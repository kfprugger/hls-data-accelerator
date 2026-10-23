import os, sys, time, json, random, traceback
from datetime import datetime

# Force stdout/stderr to be unbuffered for ACI logging
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("=== MULTI-DEVICE EMULATOR STARTING ===", flush=True)

try:
    from azure.eventhub import EventHubProducerClient, EventData
    from azure.identity import ManagedIdentityCredential
    print("Imports successful", flush=True)
except Exception as e:
    print(f"Import error: {e}", flush=True)
    traceback.print_exc()
    time.sleep(60)
    sys.exit(1)

# Configuration - Using Managed Identity (no connection strings/secrets needed!)
EVENT_HUB_NAMESPACE = os.getenv('EVENT_HUB_NAMESPACE')  # e.g., masimo-eh-ns
EVENT_HUB_NAME = os.getenv('EVENT_HUB_NAME')
DEVICE_COUNT = int(os.getenv('DEVICE_COUNT', '100'))

print(f"EVENT_HUB_NAMESPACE: {EVENT_HUB_NAMESPACE}", flush=True)
print(f"EVENT_HUB_NAME: {EVENT_HUB_NAME}", flush=True)
print(f"DEVICE_COUNT: {DEVICE_COUNT}", flush=True)

# Generate deterministic device IDs that match FHIR Device resources
DEVICE_IDS = [f"MASIMO-RADIUS7-{i:04d}" for i in range(1, DEVICE_COUNT + 1)]
print(f"Devices: {DEVICE_IDS[0]} to {DEVICE_IDS[-1]}", flush=True)

class MasimoSimulator:
    """Simulates a single Masimo Radius-7 pulse oximeter"""
    def __init__(self, device_id: str):
        self.device_id = device_id
        # Initialize with slightly different baselines per device
        seed = hash(device_id) % 1000
        random.seed(seed)
        # Keep 3 devices in an alerting band for demo alerting while 97% mean-revert to healthy baselines
        is_alert_device = device_id.endswith(("0021", "0033", "0085"))
        self.target_spo2 = 90.5 if is_alert_device else (96.5 + random.uniform(0, 2.5))
        self.target_pr = 118.0 if is_alert_device else (68.0 + random.uniform(0, 18))
        self.target_pi = 2.5 + random.uniform(0, 2)
        self.target_pvi = 10.0 + random.uniform(0, 8)
        self.spo2 = self.target_spo2
        self.pr = self.target_pr
        self.pi = self.target_pi
        self.pvi = self.target_pvi
        random.seed()  # Re-randomize
        
    def generate_reading(self):
        # Ornstein-Uhlenbeck mean-reversion toward each device's physiological baseline
        self.spo2 += 0.15 * (self.target_spo2 - self.spo2) + random.uniform(-0.4, 0.4)
        self.pr += 0.15 * (self.target_pr - self.pr) + random.uniform(-1.5, 1.5)
        self.pi += 0.10 * (self.target_pi - self.pi) + random.uniform(-0.1, 0.1)
        self.pvi += 0.10 * (self.target_pvi - self.pvi) + random.uniform(-1, 1)
        
        # Clamp to realistic ranges
        self.spo2 = max(88, min(100, self.spo2))
        self.pr = max(50, min(140, self.pr))
        self.pi = max(0.5, min(10, self.pi))
        self.pvi = max(5, min(30, self.pvi))
        
        payload = {
            "device_id": self.device_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "telemetry": {
                "spo2": round(self.spo2, 1),
                "pr": int(self.pr),
                "pi": round(self.pi, 2),
                "pvi": int(self.pvi),
                "sphb": round(12.5 + random.uniform(-1, 1), 1),
                "signal_iq": random.randint(90, 100)
            }
        }
        return payload

def run():
    print("Connecting to Event Hub using Managed Identity...", flush=True)
    credential = ManagedIdentityCredential()
    fully_qualified_namespace = f"{EVENT_HUB_NAMESPACE}.servicebus.windows.net"
    print(f"FQNS: {fully_qualified_namespace}", flush=True)
    simulators = {device_id: MasimoSimulator(device_id) for device_id in DEVICE_IDS}
    print(f"Created {len(simulators)} device simulators", flush=True)
    cycle = 0
    attempt = 0
    while True:
        try:
            print("Creating producer...", flush=True)
            producer = EventHubProducerClient(
                fully_qualified_namespace=fully_qualified_namespace,
                eventhub_name=EVENT_HUB_NAME,
                credential=credential
            )
            print("Entering producer context...", flush=True)
            with producer:
                attempt = 0
                print("Starting multi-device telemetry loop...", flush=True)
                while True:
                    batch = producer.create_batch()
                    for device_id in DEVICE_IDS:
                        sim = simulators[device_id]
                        data = sim.generate_reading()
                        try:
                            batch.add(EventData(json.dumps(data)))
                        except ValueError:
                            producer.send_batch(batch)
                            batch = producer.create_batch()
                            batch.add(EventData(json.dumps(data)))
                    producer.send_batch(batch)
                    cycle += 1
                    if cycle % 10 == 0:
                        print(f"Cycle {cycle}: Sent telemetry for {len(DEVICE_IDS)} devices", flush=True)
                    time.sleep(1)
        except Exception as e:
            attempt += 1
            delay = min(30, 2 ** min(attempt, 5))
            print(f"!!! Transient Producer Error (attempt {attempt}, reconnecting in {delay}s): {e}", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
            time.sleep(delay)
if __name__ == "__main__":
    run()
