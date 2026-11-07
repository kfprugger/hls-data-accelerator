#!/usr/bin/env python3
"""Seed TCGA 15-patient synthetic cohort into FHIR R4 service.

Generates FHIR R4 Patient, Condition, MedicationRequest, Observation,
Coverage, Device, and Basic (device-assoc) resources using deterministic
UUIDv5 IDs and the 'synthetic-demo-enrichment' provenance tag.

Supports three subcommands:
  plan   (default) - Inspects target FHIR service, reports planned counts, exits 0 dry-run.
  apply            - Uploads transaction bundles after verifying overwrite safety.
  delete           - Removes only resources bearing the synthetic-demo-enrichment tag.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid5

# Socket binding for en0 under VPN on macOS
if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    try:
        import urllib3.util.connection
        _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
        _orig_conn = urllib3.util.connection.create_connection

        def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
            opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
            return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)

        urllib3.util.connection.create_connection = _bound_conn
    except Exception:
        pass

# Ensure fabric_config does not fail on import when dummy envs are missing
for _k in (
    "WORKSPACE_ID", "WORKSPACE_NAME", "LAKEHOUSE_ID", "LAKEHOUSE_NAME",
    "CLINICAL_LH", "GENOMICS_LH", "IMAGING_LH", "PATIENT360_LH",
    "GOLD_LH", "PATIENT360_SQL", "PATIENT360_SQL_SERVER",
):
    if _k not in os.environ:
        os.environ[_k] = "placeholder"

ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "rayfin-imaging" / "pipeline"
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(ROOT / "synthea"))

try:
    from seed_patient360_silos import PATIENT_META, CANCER_NAMES, ORGANS
except ImportError:
    # Standalone fallback if pipeline package not in path
    PATIENT_META = {}
    CANCER_NAMES = {}
    ORGANS = {}

NAMESPACE = UUID("73590e85-86db-46ab-8a17-549b208963cc")
PROVENANCE_SYSTEM = "https://brakekat.com/hls/demo-provenance"
SYNTHETIC_TAG_CODE = "synthetic-demo-enrichment"
SYNTHETIC_TAG_DISPLAY = "Synthetic demo source; not an observed clinical event"

CANCER_SNOMED: dict[str, tuple[str, str]] = {
    "KIRC": ("35917007", "Clear cell adenocarcinoma of kidney"),
    "BRCA": ("254837009", "Malignant neoplasm of breast"),
    "LUAD": ("254637007", "Non-small cell lung cancer"),
    "LUSC": ("254637007", "Squamous cell carcinoma of lung"),
    "OV": ("363443007", "Malignant neoplasm of ovary"),
    "LIHC": ("25370001", "Hepatocellular carcinoma"),
    "BLCA": ("399326009", "Malignant neoplasm of urinary bladder"),
    "UCEC": ("254878004", "Malignant neoplasm of endometrium"),
    "CESC": ("363406005", "Malignant neoplasm of cervix"),
    "STAD": ("363349007", "Malignant neoplasm of stomach"),
    "COAD": ("269533000", "Malignant neoplasm of colon"),
    "ESCA": ("363402007", "Malignant neoplasm of esophagus"),
    "KICH": ("254884004", "Chromophobe renal cell carcinoma"),
    "KIRP": ("254884004", "Papillary renal cell carcinoma"),
    "PRAD": ("399068003", "Malignant neoplasm of prostate"),
}


def resource_id(*parts: object) -> str:
    """Generate deterministic UUIDv5 under the HLS demo namespace."""
    return str(uuid5(NAMESPACE, ":".join(map(str, parts))))


def provenance_meta() -> dict:
    return {
        "tag": [{
            "system": PROVENANCE_SYSTEM,
            "code": SYNTHETIC_TAG_CODE,
            "display": SYNTHETIC_TAG_DISPLAY,
        }]
    }


def is_synthetic_tagged(resource: dict) -> bool:
    """Check if resource carries the synthetic-demo-enrichment tag."""
    tags = resource.get("meta", {}).get("tag", [])
    return any(t.get("code") == SYNTHETIC_TAG_CODE for t in tags)


def load_cohort(cohort_path: pathlib.Path | None = None) -> list[dict]:
    path = cohort_path or (PIPELINE / "cohort.json")
    if not path.is_file():
        raise FileNotFoundError(f"Cohort configuration not found: {path}")
    data = json.loads(path.read_text())
    patients = data.get("patients", [])
    if not patients:
        sys.stderr.write(f"Error: Empty cohort configuration in {path}\n")
        sys.exit(1)
    return patients


def build_patient(pid: str, m: dict) -> dict:
    p_id = resource_id("Patient", pid)
    parts = m["name"].split()
    family = parts[-1].capitalize()
    given = [p.capitalize() for p in parts[:-1]]
    display_name = f"{' '.join(given)} {family}"
    birth_year = m["year"] - m["age"]
    gender = "male" if m["sex"].lower() == "male" else "female"

    return {
        "resourceType": "Patient",
        "id": p_id,
        "meta": provenance_meta(),
        "identifier": [
            {
                "system": "https://gdc.cancer.gov/tcga/barcode",
                "value": pid,
            }
        ],
        "name": [
            {
                "use": "official",
                "family": family,
                "given": given,
                "text": display_name,
            }
        ],
        "gender": gender,
        "birthDate": f"{birth_year:04d}-01-01",
        "address": [
            {
                "country": "United States",
            }
        ],
    }


def build_condition(pid: str, m: dict, code: str) -> dict:
    patient_res_id = resource_id("Patient", pid)
    cancer_name = CANCER_NAMES.get(code, "Malignant Neoplasm")
    day_offset = int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 280 + 20
    icd10 = f"C{15 + (day_offset % 65)}.9"
    snomed_code, snomed_display = CANCER_SNOMED.get(code, ("35917007", cancer_name))
    cond_id = resource_id(patient_res_id, "condition", code)

    return {
        "resourceType": "Condition",
        "id": cond_id,
        "meta": provenance_meta(),
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": "active",
                "display": "Active",
            }]
        },
        "verificationStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                "code": "confirmed",
                "display": "Confirmed",
            }]
        },
        "code": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                    "code": icd10,
                    "display": cancer_name,
                },
                {
                    "system": "http://snomed.info/sct",
                    "code": snomed_code,
                    "display": cancer_name,
                },
            ],
            "text": cancer_name,
        },
        "subject": {
            "reference": f"Patient/{patient_res_id}",
        },
        "stage": [
            {
                "summary": {
                    "coding": [{
                        "system": "http://snomed.info/sct",
                        "code": "258219007",
                        "display": m["stage"],
                    }],
                    "text": m["stage"],
                }
            }
        ],
        "recordedDate": f"{m['year']}-01-01",
    }


def build_medications(pid: str, m: dict) -> list[dict]:
    patient_res_id = resource_id("Patient", pid)
    meds = []
    treatments = m.get("treatments", [])
    for j, (ttype, agent, s_day, e_day, outc) in enumerate(treatments):
        display_name = agent if agent else ttype
        is_active = (
            "ongoing" in str(outc).lower()
            or (j == len(treatments) - 1 and m.get("vital") != "Dead")
        )
        status = "active" if is_active else "completed"
        med_id = resource_id(patient_res_id, "medication", j, display_name)
        start_date = dt.date(m["year"], 1, 1) + dt.timedelta(days=max(0, s_day))
        meds.append({
            "resourceType": "MedicationRequest",
            "id": med_id,
            "meta": provenance_meta(),
            "status": status,
            "intent": "order",
            "subject": {
                "reference": f"Patient/{patient_res_id}",
            },
            "authoredOn": start_date.isoformat(),
            "medicationCodeableConcept": {
                "coding": [{
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "display": display_name,
                }],
                "text": display_name,
            },
        })
    return meds


def build_observations(pid: str, m: dict) -> list[dict]:
    patient_res_id = resource_id("Patient", pid)
    obs = []
    vitals = [
        ("8480-6", "Systolic blood pressure", 125.0 if pid == "TCGA-G6-A8L6" else 120.0 + (m["age"] % 15), "mmHg", "mm[Hg]"),
        ("8462-4", "Diastolic blood pressure", 82.0 if pid == "TCGA-G6-A8L6" else 78.0 + (m["age"] % 10), "mmHg", "mm[Hg]"),
        ("8867-4", "Heart rate", 74.0 if pid == "TCGA-G6-A8L6" else 72.0 + (m["age"] % 8), "/min", "/min"),
        ("39156-5", "Body mass index (BMI) [Ratio]", float(m["bmi"]), "kg/m2", "kg/m2"),
        ("2708-6", "Oxygen saturation in Arterial blood", 97.0, "%", "%"),
    ]
    effective_dt = f"{m['year']}-01-01T08:00:00Z"
    for loinc, name, val, unit, code in vitals:
        obs_id = resource_id(patient_res_id, "observation", loinc)
        obs.append({
            "resourceType": "Observation",
            "id": obs_id,
            "meta": provenance_meta(),
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "vital-signs",
                    "display": "Vital Signs",
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": loinc,
                    "display": name,
                }],
                "text": name,
            },
            "subject": {
                "reference": f"Patient/{patient_res_id}",
            },
            "effectiveDateTime": effective_dt,
            "valueQuantity": {
                "value": round(val, 1),
                "unit": unit,
                "system": "http://unitsofmeasure.org",
                "code": code,
            },
        })
    return obs


def build_coverage(pid: str, m: dict) -> dict:
    patient_res_id = resource_id("Patient", pid)
    is_medicare = m["age"] >= 65
    payer_name = "Synthetic Medicare" if is_medicare else "Synthetic Commercial"
    payer_code = "MCR" if is_medicare else "COMM"
    payer_org_id = resource_id("payer", "Medicare" if is_medicare else "Commercial")
    cov_id = resource_id(patient_res_id, "coverage")
    return {
        "resourceType": "Coverage",
        "id": cov_id,
        "meta": provenance_meta(),
        "status": "active",
        "beneficiary": {
            "reference": f"Patient/{patient_res_id}",
        },
        "payor": [{
            "reference": f"Organization/{payer_org_id}",
            "display": payer_name,
        }],
        "type": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": payer_code,
                "display": payer_name,
            }],
            "text": payer_name,
        },
        "period": {
            "start": f"{m['year']}-01-01",
        },
    }


def build_device(device_id: str) -> dict:
    return {
        "resourceType": "Device",
        "id": device_id,
        "meta": provenance_meta(),
        "identifier": [
            {
                "system": "http://masimo.com/devices",
                "value": device_id,
            }
        ],
        "status": "active",
        "modelNumber": "Radius-7",
        "type": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "706767009",
                    "display": "Pulse oximeter",
                }
            ],
            "text": "Pulse Oximeter",
        },
        "deviceName": [
            {
                "name": f"Masimo Radius-7 ({device_id})",
                "type": "user-friendly-name",
            }
        ],
    }


def build_device_association(patient_resource_id: str, patient_name: str, device_id: str) -> dict:
    return {
        "resourceType": "Basic",
        "id": resource_id(patient_resource_id, "device-assoc"),
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Basic"],
            "tag": [{
                "system": PROVENANCE_SYSTEM,
                "code": SYNTHETIC_TAG_CODE,
                "display": SYNTHETIC_TAG_DISPLAY,
            }],
        },
        "code": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/basic-resource-type",
                    "code": "device-assoc",
                    "display": "Device Association",
                }
            ],
            "text": "Device Assignment",
        },
        "subject": {
            "reference": f"Patient/{patient_resource_id}",
            "display": patient_name,
        },
        "extension": [
            {
                "url": "http://example.org/StructureDefinition/associated-device",
                "valueReference": {
                    "reference": f"Device/{device_id}",
                    "display": f"Masimo Radius-7 - {device_id}",
                },
            },
            {
                "url": "http://example.org/StructureDefinition/association-status",
                "valueCode": "active",
            },
        ],
    }


def generate_cohort_resources(patients: list[dict]) -> list[dict]:
    """Generate all FHIR R4 resources for the TCGA cohort."""
    resources: list[dict] = []
    for idx, p in enumerate(patients):
        pid = p["id"]
        code = p["project"].split("-")[1]
        m = PATIENT_META[pid]
        p_res = build_patient(pid, m)
        resources.append(p_res)
        patient_res_id = p_res["id"]
        patient_display_name = p_res["name"][0]["text"]

        # Primary Condition
        resources.append(build_condition(pid, m, code))

        # MedicationRequests
        resources.extend(build_medications(pid, m))

        # Observations
        resources.extend(build_observations(pid, m))

        # Coverage
        resources.append(build_coverage(pid, m))

        # Device pairing per router decision: Marcus Vance = MASIMO-RADIUS7-0101, others 0102..0115
        device_id = "MASIMO-RADIUS7-0101" if pid == "TCGA-G6-A8L6" else f"MASIMO-RADIUS7-{101 + idx:04d}"
        resources.append(build_device(device_id))
        resources.append(build_device_association(patient_res_id, patient_display_name, device_id))

    return resources


def transaction_bundles(resources: list[dict], batch_size: int = 100):
    if batch_size < 1 or batch_size > 400:
        raise ValueError("FHIR transaction batch size must be between 1 and 400")
    for offset in range(0, len(resources), batch_size):
        yield {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {
                    "fullUrl": f"urn:uuid:{r['id']}",
                    "resource": r,
                    "request": {
                        "method": "PUT",
                        "url": f"{r['resourceType']}/{r['id']}",
                    },
                }
                for r in resources[offset:offset + batch_size]
            ],
        }


def check_safe_overwrite(client: FHIRClient, resources: list[dict]) -> None:
    """Verify that no pre-existing resource without synthetic tag will be overwritten."""
    by_type: dict[str, list[dict]] = {}
    for r in resources:
        by_type.setdefault(r["resourceType"], []).append(r)

    for rtype, rlist in by_type.items():
        ids = [r["id"] for r in rlist]
        if len(ids) == 1:
            status, _, data = client.request("GET", f"{rtype}/{ids[0]}")
            if status == 200:
                if not is_synthetic_tagged(data):
                    msg = f"Refusing to overwrite existing non-synthetic resource: {rtype}/{ids[0]}\n"
                    sys.stderr.write(msg)
                    sys.exit(3)
            continue

        try:
            id_str = ",".join(ids)
            status, _, bundle = client.request("GET", f"{rtype}?_id={id_str}&_count=200")
            if status == 200 and bundle.get("resourceType") == "Bundle":
                for entry in bundle.get("entry", []):
                    res = entry.get("resource", {})
                    if is_synthetic_tagged(res):
                        continue
                    # Check if it is a tombstone of a deleted resource
                    has_content = bool(set(res.keys()) - {"id", "resourceType", "meta"})
                    if not has_content:
                        s, _, _ = client.request("GET", f"{rtype}/{res.get('id')}")
                        if s in (404, 410):
                            continue
                    msg = f"Refusing to overwrite existing non-synthetic resource: {res.get('resourceType', rtype)}/{res.get('id')}\n"
                    sys.stderr.write(msg)
                    sys.exit(3)
                continue
        except Exception:
            pass

        for r in rlist:
            rid = r["id"]
            status, _, data = client.request("GET", f"{rtype}/{rid}")
            if status == 200:
                if not is_synthetic_tagged(data):
                    msg = f"Refusing to overwrite existing non-synthetic resource: {rtype}/{rid}\n"
                    sys.stderr.write(msg)
                    sys.exit(3)


def run_delete(client: FHIRClient, resources: list[dict]) -> int:
    by_type: dict[str, list[dict]] = {}
    for r in resources:
        by_type.setdefault(r["resourceType"], []).append(r)

    existing_map: dict[str, dict] = {}
    for rtype, rlist in by_type.items():
        ids = [r["id"] for r in rlist]
        try:
            id_str = ",".join(ids)
            status, _, bundle = client.request("GET", f"{rtype}?_id={id_str}&_count=200")
            if status == 200 and bundle.get("resourceType") == "Bundle":
                for entry in bundle.get("entry", []):
                    res = entry.get("resource", {})
                    if res.get("id"):
                        has_content = bool(set(res.keys()) - {"id", "resourceType", "meta"})
                        if not has_content:
                            s, _, _ = client.request("GET", f"{rtype}/{res.get('id')}")
                            if s in (404, 410):
                                continue
                        existing_map[f"{rtype}/{res['id']}"] = res
                continue
        except Exception:
            pass

        for r in rlist:
            rid = r["id"]
            status, _, data = client.request("GET", f"{rtype}/{rid}")
            if status == 200:
                existing_map[f"{rtype}/{rid}"] = data

    deleted_count = 0
    skipped_count = 0
    for path, data in existing_map.items():
        if is_synthetic_tagged(data):
            d_status, _, _ = client.request("DELETE", path)
            if d_status in (200, 204):
                deleted_count += 1
            else:
                raise RuntimeError(f"Failed to delete {path}: HTTP {d_status}")
        else:
            skipped_count += 1
            print(f"Skipping untagged resource {path} during deletion")

    print(f"Cleanup summary: Deleted {deleted_count} synthetic resources, skipped {skipped_count} untagged resources.")
    return deleted_count

def validate_origin(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        sys.stderr.write("Refusing to send credentials to untrusted API origin\n")
        sys.exit(2)
    host = (parsed.hostname or "").lower()
    trusted = (
        host.endswith(".azurehealthcareapis.com")
        or host.endswith(".azurehealthcareapis.net")
        or host in ("localhost", "127.0.0.1", "mock-fhir.azurehealthcareapis.com")
        or os.environ.get("HLS_ALLOW_TEST_ORIGIN") == "1"
    )
    if not trusted:
        sys.stderr.write("Refusing to send credentials to untrusted API origin\n")
        sys.exit(2)


class FHIRClient:
    def __init__(self, base_url: str, subscription: str | None = None, token: str | None = None):
        validate_origin(base_url)
        self.base = base_url.rstrip("/")
        self.subscription = subscription
        self._token = token or ""
        self._expires = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        if os.environ.get("HLS_FHIR_TOKEN"):
            self._token = os.environ["HLS_FHIR_TOKEN"]
            self._expires = time.time() + 3600
            return self._token

        az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure"))
        msal_path = az_dir / "msal_token_cache.json"
        if msal_path.is_file():
            try:
                msal = json.loads(msal_path.read_text())
                rt_entry = next(iter(msal.get("RefreshToken", {}).values()))
                profiles = json.loads((az_dir / "azureProfile.json").read_bytes().decode("utf-8-sig"))
                tenant = next((s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")), "organizations")
                r = requests_post_safe(
                    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    data={
                        "client_id": rt_entry["client_id"],
                        "grant_type": "refresh_token",
                        "refresh_token": rt_entry["secret"],
                        "scope": f"{self.base}/.default offline_access",
                    },
                    timeout=20,
                )
                if r.status_code == 200 and "access_token" in r.json():
                    b = r.json()
                    self._token = b["access_token"]
                    self._expires = time.time() + float(b.get("expires_in", 3600))
                    return self._token
            except Exception:
                pass

        # az CLI fallback
        cmd = ["az", "account", "get-access-token", "--resource", self.base]
        if self.subscription:
            cmd.extend(["--subscription", self.subscription])
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            parsed = json.loads(res.stdout)
            self._token = parsed["accessToken"]
            self._expires = time.time() + 1800
            return self._token

        if self.subscription:
            # Fallback without --subscription in case sub was dummy
            res = subprocess.run(["az", "account", "get-access-token", "--resource", self.base], capture_output=True, text=True)
            if res.returncode == 0:
                parsed = json.loads(res.stdout)
                self._token = parsed["accessToken"]
                self._expires = time.time() + 1800
                return self._token

        try:
            from azure.identity import AzureCliCredential
            cred = AzureCliCredential(process_timeout=30)
            tok = cred.get_token(f"{self.base}/.default")
            self._token = tok.token
            self._expires = float(tok.expires_on)
            return self._token
        except Exception:
            pass

        return ""

    def request(self, method: str, path: str, body: dict | None = None, max_retries: int = 3):
        url = urljoin(self.base + "/", path.lstrip("/"))
        if urlsplit(url)[:2] != urlsplit(self.base)[:2]:
            raise RuntimeError("Refusing to send credentials to a different API origin")

        tok = self.get_token()
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/json",
        }
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

        data = json.dumps(body).encode("utf-8") if body is not None else None

        for attempt in range(max_retries):
            req = Request(url, data=data, headers=headers, method=method)
            try:
                with urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                    parsed = json.loads(raw.decode("utf-8")) if raw else {}
                    return resp.status, resp.headers, parsed
            except HTTPError as err:
                if err.code == 429:
                    retry_after = err.headers.get("Retry-After") if err.headers else None
                    wait_sec = float(retry_after) if retry_after else float(2 ** attempt)
                    wait_sec = min(wait_sec, 30.0)
                    if attempt < max_retries - 1:
                        time.sleep(wait_sec)
                        continue
                    else:
                        raise RuntimeError(f"FHIR server 429 throttling after {max_retries} retries: {err.read().decode('utf-8', errors='replace')}") from err
                if err.code in (404, 410):
                    return err.code, err.headers, {}
                raw_err = err.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"{method} {path} HTTP {err.code}: {raw_err}") from None


def requests_post_safe(url: str, data: dict, timeout: int = 20):
    import requests
    return requests.post(url, data=data, timeout=timeout)


def discover_fhir_url(resource_group: str, subscription: str | None = None) -> str:
    """Discover AHDS FHIR service audience URL in resource group."""
    cmd = ["az", "resource", "list", "-g", resource_group, "--resource-type", "Microsoft.HealthcareApis/workspaces/fhirservices", "-o", "json"]
    if subscription:
        cmd.extend(["--subscription", subscription])
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 and subscription:
        cmd = ["az", "resource", "list", "-g", resource_group, "--resource-type", "Microsoft.HealthcareApis/workspaces/fhirservices", "-o", "json"]
        res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        items = json.loads(res.stdout)
        if items:
            fhir_id = items[0]["id"]
            show_cmd = ["az", "resource", "show", "--ids", fhir_id, "--api-version", "2022-06-01", "-o", "json"]
            show_res = subprocess.run(show_cmd, capture_output=True, text=True)
            if show_res.returncode == 0:
                props = json.loads(show_res.stdout).get("properties", {})
                audience = props.get("authenticationConfiguration", {}).get("audience")
                if audience:
                    return audience.rstrip("/")
    raise RuntimeError(f"Could not discover FHIR service in resource group {resource_group}")


def run_plan(resources: list[dict]) -> None:
    counts: dict[str, int] = {}
    for r in resources:
        rt = r["resourceType"]
        counts[rt] = counts.get(rt, 0) + 1

    print("Planned FHIR resources for TCGA cohort:")
    print(f"  Patient: {counts.get('Patient', 0)}")
    print(f"  Condition: {counts.get('Condition', 0)}")
    print(f"  MedicationRequest: {counts.get('MedicationRequest', 0)}")
    print(f"  Observation: {counts.get('Observation', 0)}")
    print(f"  Coverage: {counts.get('Coverage', 0)}")
    print(f"  Device: {counts.get('Device', 0)}")
    print(f"  Basic (DeviceAssociation): {counts.get('Basic', 0)}")
    print("Dry-run plan mode: 0 resources written or modified.")


def run_apply(client: FHIRClient, resources: list[dict]) -> dict[str, int]:
    # 1. Check safe overwrite protection before modifying any record
    check_safe_overwrite(client, resources)

    # 2. Upload in transaction bundles
    applied_counts: dict[str, int] = {}
    for bundle in transaction_bundles(resources, batch_size=100):
        status, headers, resp = client.request("POST", "", body=bundle)
        if status not in (200, 201):
            raise RuntimeError(f"FHIR transaction bundle failed with HTTP {status}: {resp}")
        for entry in resp.get("entry", []):
            estatus = str(entry.get("response", {}).get("status", ""))
            if not estatus.startswith(("200", "201")):
                raise RuntimeError(f"Transaction entry failed: {entry}")

    for r in resources:
        rt = r["resourceType"]
        applied_counts[rt] = applied_counts.get(rt, 0) + 1

    # Report exact format: FHIR upsert counts: {"Basic": 15, "Condition": ..., ...}
    print(f"FHIR upsert counts: {json.dumps(applied_counts, sort_keys=True)}")
    return applied_counts

def emit_baseline_telemetry(
    resource_group: str | None = None,
    subscription: str | None = None,
    namespace: str | None = None,
    eh_name: str = "telemetry-stream",
) -> int:
    """Emit 10 baseline telemetry readings per TCGA device (MASIMO-RADIUS7-0101..0115) to Masimo Event Hub."""
    ns = namespace
    if not ns:
        if not resource_group:
            print("Skipping baseline telemetry emission: no Event Hub namespace or resource group provided")
            return 0
        cmd = ["az", "eventhubs", "namespace", "list", "-g", resource_group, "-o", "json"]
        if subscription:
            cmd.extend(["--subscription", subscription])
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 and subscription:
            cmd = ["az", "eventhubs", "namespace", "list", "-g", resource_group, "-o", "json"]
            res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            items = json.loads(res.stdout)
            if items:
                ns = items[0]["name"]
        if not ns:
            raise RuntimeError(f"Could not discover Event Hub namespace in {resource_group}")

    cmd_tok = ["az", "account", "get-access-token", "--resource", "https://eventhubs.azure.net", "-o", "json"]
    if subscription:
        cmd_tok.extend(["--subscription", subscription])
    res_tok = subprocess.run(cmd_tok, capture_output=True, text=True)
    if res_tok.returncode != 0 and subscription:
        res_tok = subprocess.run(["az", "account", "get-access-token", "--resource", "https://eventhubs.azure.net", "-o", "json"], capture_output=True, text=True)
    if res_tok.returncode != 0:
        try:
            from azure.identity import AzureCliCredential
            cred = AzureCliCredential(process_timeout=30)
            token = cred.get_token("https://eventhubs.azure.net/.default").token
        except Exception as e:
            raise RuntimeError(f"Could not acquire Event Hub token: {e}") from e
    else:
        token = json.loads(res_tok.stdout)["accessToken"]

    url = f"https://{ns}.servicebus.windows.net/{eh_name}/messages"
    total_sent = 0
    now = dt.datetime.now(dt.timezone.utc)
    for dev_idx in range(15):
        dev_id = f"MASIMO-RADIUS7-{101 + dev_idx:04d}"
        for r_idx in range(10):
            ts = (now - dt.timedelta(seconds=(10 - r_idx) * 2)).isoformat().replace("+00:00", "Z")
            payload = {
                "device_id": dev_id,
                "timestamp": ts,
                "telemetry": {
                    "spo2": round(96.0 + (dev_idx % 3) * 0.5 + (r_idx % 3) * 0.2, 1),
                    "pr": int(68 + (dev_idx % 10) + (r_idx % 4)),
                    "pi": 2.5,
                    "pvi": 12,
                    "sphb": 13.0,
                    "signal_iq": 98,
                },
            }
            data = json.dumps(payload).encode("utf-8")
            req = Request(url, data=data, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }, method="POST")
            try:
                with urlopen(req, timeout=30) as resp:
                    if resp.status not in (200, 201):
                        raise RuntimeError(f"Event Hub POST returned {resp.status}")
                total_sent += 1
            except HTTPError as err:
                if err.code in (401, 403):
                    raise RuntimeError("denied (no Data Sender role)") from err
                raise

    print(f"Emitted {total_sent} baseline telemetry events for devices MASIMO-RADIUS7-0101..0115 to {ns}/{eh_name}")
    return total_sent




def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--fhir-url", help="Target FHIR service URL")
    parent.add_argument("--resource-group", "-g", help="Azure Resource Group containing FHIR service")
    parent.add_argument("--subscription", help="Azure Subscription ID")
    parent.add_argument("--as-of", help="Simulated as-of date (YYYY-MM-DD)")
    parent.add_argument("--cohort-path", help="Path to cohort.json", type=pathlib.Path)
    parent.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parent.add_argument("--emit-baseline-telemetry", action="store_true", help="Emit 10 baseline telemetry readings per TCGA device to Masimo Event Hub")
    parent.add_argument("--eventhub-namespace", help="Masimo Event Hub namespace")
    parent.add_argument("--eventhub-name", default="telemetry-stream", help="Event Hub name (default: telemetry-stream)")
    parser = argparse.ArgumentParser(
        description="TCGA Cohort Synthetic FHIR, Device, and Claim Ingestion",
        parents=[parent],
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("plan", parents=[parent], help="Dry-run planning mode")
    sub.add_parser("apply", parents=[parent], help="Upload transaction bundles")
    sub.add_parser("delete", parents=[parent], help="Delete tagged synthetic resources")

    args = parser.parse_args(argv)
    if not args.command:
        args.command = "plan"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    cohort = load_cohort(args.cohort_path)
    resources = generate_cohort_resources(cohort)

    if args.command == "plan":
        # In plan mode, if fhir-url is provided, validate origin
        if args.fhir_url:
            validate_origin(args.fhir_url)
        run_plan(resources)
        return 0

    fhir_url = args.fhir_url
    if not fhir_url:
        if args.resource_group:
            fhir_url = discover_fhir_url(args.resource_group, args.subscription)
        else:
            sys.stderr.write("Error: Either --fhir-url or --resource-group must be provided.\n")
            return 1

    validate_origin(fhir_url)
    client = FHIRClient(fhir_url, subscription=args.subscription)

    if args.command == "apply":
        run_apply(client, resources)
        if getattr(args, "emit_baseline_telemetry", False):
            emit_baseline_telemetry(
                resource_group=args.resource_group,
                subscription=args.subscription,
                namespace=args.eventhub_namespace,
                eh_name=args.eventhub_name,
            )
        return 0
    elif args.command == "delete":
        run_delete(client, resources)
        return 0
    else:
        sys.stderr.write(f"Unknown command: {args.command}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
