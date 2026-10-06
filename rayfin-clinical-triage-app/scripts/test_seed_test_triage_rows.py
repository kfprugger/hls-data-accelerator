import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("seed_test_triage_rows", Path(__file__).with_name("seed_test_triage_rows.py"))
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)

# dbo.AlertTriages column limits (nvarchar max lengths) from the deployed schema.
LIMITS = {"patientId": 64, "vitalsType": 64, "severity": 8, "status": 12, "clinicianNotes": 1000, "patientAlias": 32,
          "alertTier": 16, "locationName": 160, "deviceId": 64, "alertReason": 64, "spo2": 16, "pulseRate": 16,
          "assignedTo": 80, "escalationLevel": 32, "disposition": 64}


def alert(device: str, tier: str, minute: int) -> dict:
    return {"alert_time": f"2026-10-06T04:{minute:02d}:00Z", "device_id": device, "patient_id": "a22e741b-2340-2f7c-2b4a-4e0bb5fe2f0b",
            "patient_name": "Adolph80 Bogan287", "alert_tier": tier, "alert_type": "SPO2_LOW", "spo2": 88.5, "pr": 96,
            "location_name": "Emory Saint Joseph's Hospital"}


class SeedTestTriageRowsTests(unittest.TestCase):
    def test_rows_fit_the_table_and_mask_the_patient(self) -> None:
        alerts = [alert(f"MASIMO-{i:04d}", tier, i) for i, tier in enumerate(["CRITICAL", "URGENT", "WARNING"] * 4)]
        rows = [seed.triage_row(a, i) for i, a in enumerate(seed.select_alerts(alerts, 12))]

        for row in rows:
            self.assertIn(row["severity"], ("Warning", "Critical"))
            self.assertIn(row["status"], ("Open", "Acknowledged", "Resolved"))
            for column, limit in LIMITS.items():
                if row[column] is not None:
                    self.assertLessEqual(len(row[column]), limit, column)
            self.assertNotIn("Bogan287", row["patientAlias"])
            self.assertEqual(row["patientAlias"], "A. Bogan")
        self.assertEqual({r["alertTier"] for r in rows}, {"Critical", "Urgent", "Warning"})
        self.assertEqual({r["status"] for r in rows}, {"Open", "Acknowledged", "Resolved"})
        self.assertEqual(rows[0]["alertReason"], "Low SpO2")

    def test_ids_are_stable_per_device_so_reruns_do_not_duplicate(self) -> None:
        first = seed.triage_row(alert("MASIMO-0001", "CRITICAL", 1), 0)
        rerun = seed.triage_row(alert("MASIMO-0001", "URGENT", 9), 4)
        other = seed.triage_row(alert("MASIMO-0002", "CRITICAL", 1), 0)
        self.assertEqual(first["id"], rerun["id"])
        self.assertNotEqual(first["id"], other["id"])


if __name__ == "__main__":
    unittest.main()
