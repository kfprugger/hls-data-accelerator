from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

SYNTHEA_DIR = Path(__file__).resolve().parents[1]
if str(SYNTHEA_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTHEA_DIR))

import seed_tcga_cohort


class TestSeedTcgaCohort(unittest.TestCase):
    def setUp(self):
        self.cohort = seed_tcga_cohort.load_cohort()
        self.resources = seed_tcga_cohort.generate_cohort_resources(self.cohort)

    def test_cohort_size_and_marcus_vance_pairing(self):
        # Marcus Vance is TCGA-G6-A8L6
        patients = [r for r in self.resources if r["resourceType"] == "Patient"]
        self.assertEqual(15, len(patients))
        marcus = next((p for p in patients if any(i.get("value") == "TCGA-G6-A8L6" for i in p.get("identifier", []))), None)
        self.assertIsNotNone(marcus)
        self.assertEqual("Vance", marcus["name"][0]["family"])
        self.assertEqual(["Marcus"], marcus["name"][0]["given"])
        self.assertEqual("male", marcus["gender"])

        # Check Marcus Vance device association
        basics = [r for r in self.resources if r["resourceType"] == "Basic"]
        self.assertEqual(15, len(basics))
        marcus_basic = next((b for b in basics if b["subject"]["reference"] == f"Patient/{marcus['id']}"), None)
        self.assertIsNotNone(marcus_basic)
        self.assertEqual("device-assoc", marcus_basic["code"]["coding"][0]["code"])
        device_ref = marcus_basic["extension"][0]["valueReference"]["reference"]
        self.assertEqual("Device/MASIMO-RADIUS7-0101", device_ref)

        # Check Device resource
        devices = [r for r in self.resources if r["resourceType"] == "Device"]
        self.assertEqual(15, len(devices))
        marcus_device = next((d for d in devices if d["id"] == "MASIMO-RADIUS7-0101"), None)
        self.assertIsNotNone(marcus_device)
        self.assertEqual("Radius-7", marcus_device["modelNumber"])
        self.assertEqual("Pulse oximeter", marcus_device["type"]["coding"][0]["display"])

    def test_condition_and_staging_and_codes(self):
        conditions = [r for r in self.resources if r["resourceType"] == "Condition"]
        self.assertGreaterEqual(len(conditions), 15)
        for c in conditions:
            self.assertEqual("active", c["clinicalStatus"]["coding"][0]["code"])
            self.assertEqual("confirmed", c["verificationStatus"]["coding"][0]["code"])
            systems = {coding["system"] for coding in c["code"]["coding"]}
            self.assertIn("http://hl7.org/fhir/sid/icd-10-cm", systems)
            self.assertIn("http://snomed.info/sct", systems)
            self.assertTrue(len(c["stage"]) > 0)
            self.assertTrue(c["stage"][0]["summary"]["text"].startswith("Stage") or "Gleason" in c["stage"][0]["summary"]["text"])

    def test_medication_requests(self):
        meds = [r for r in self.resources if r["resourceType"] == "MedicationRequest"]
        self.assertGreaterEqual(len(meds), 30)
        for m in meds:
            self.assertEqual("order", m["intent"])
            self.assertIn(m["status"], ("active", "completed"))
            self.assertTrue("reference" in m["subject"])

    def test_observations_baseline_vitals(self):
        obs = [r for r in self.resources if r["resourceType"] == "Observation"]
        self.assertGreaterEqual(len(obs), 15)
        categories = {o["category"][0]["coding"][0]["code"] for o in obs}
        self.assertIn("vital-signs", categories)

    def test_coverage_payer_assignment(self):
        coverages = [r for r in self.resources if r["resourceType"] == "Coverage"]
        self.assertEqual(15, len(coverages))
        for cov in coverages:
            self.assertEqual("active", cov["status"])
            payer_code = cov["type"]["coding"][0]["code"]
            self.assertIn(payer_code, ("MCR", "COMM"))

    def test_all_resources_have_synthetic_tag(self):
        for r in self.resources:
            self.assertTrue(
                seed_tcga_cohort.is_synthetic_tagged(r),
                f"Resource {r['resourceType']}/{r['id']} missing synthetic tag",
            )

    def test_retry_on_429(self):
        """E-7: Simulates HTTP 429 Too Many Requests response with exponential backoff."""
        client = seed_tcga_cohort.FHIRClient("https://mock-fhir.azurehealthcareapis.com", token="mock-token")

        attempts = 0
        def fake_urlopen(req, timeout=60):
            nonlocal attempts
            attempts += 1
            # HTTPError(url, code, msg, hdrs, fp)
            headers = {"Retry-After": "0.01"}
            fp = io.BytesIO(b'{"resourceType":"OperationOutcome","issue":[{"diagnostics":"Rate limited"}]}')
            raise HTTPError(req.full_url, 429, "Too Many Requests", headers, fp)

        with patch("seed_tcga_cohort.urlopen", side_effect=fake_urlopen):
            with patch("time.sleep") as mock_sleep:
                with self.assertRaises(RuntimeError) as ctx:
                    client.request("GET", "Patient/test-1", max_retries=3)
                self.assertIn("429 throttling after 3 retries", str(ctx.exception))
                self.assertEqual(3, attempts)
                self.assertEqual(2, mock_sleep.call_count)

    def test_untagged_resource_blocks_overwrite(self):
        """E-11: Detects untagged existing resource, aborts with code 3, executes 0 PUTs."""
        client = seed_tcga_cohort.FHIRClient("https://mock-fhir.azurehealthcareapis.com", token="mock-token")

        # Mock GET returning non-synthetic resource for the first patient
        test_patient = self.resources[0]
        non_synthetic_record = {
            "resourceType": test_patient["resourceType"],
            "id": test_patient["id"],
            "meta": {"tag": [{"system": "http://other.com", "code": "real-clinical"}]},
        }

        put_called = False
        def fake_request(method, path, body=None, max_retries=3):
            nonlocal put_called
            if method == "PUT" or (method == "POST" and body and body.get("type") == "transaction"):
                put_called = True
                return 200, {}, {"entry": []}
            if method == "GET" and path == f"{test_patient['resourceType']}/{test_patient['id']}":
                return 200, {}, non_synthetic_record
            return 404, {}, {}

        client.request = fake_request

        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            with self.assertRaises(SystemExit) as cm:
                seed_tcga_cohort.run_apply(client, [test_patient])
            self.assertEqual(3, cm.exception.code)

        self.assertFalse(put_called, "PUT was submitted despite untagged collision")
        self.assertIn("Refusing to overwrite existing non-synthetic resource", stderr_buf.getvalue())

    def test_synthetic_tagged_resource_allows_overwrite(self):
        """Tagged resource with synthetic-demo-enrichment is allowed to be updated."""
        client = seed_tcga_cohort.FHIRClient("https://mock-fhir.azurehealthcareapis.com", token="mock-token")
        test_patient = self.resources[0]
        tagged_record = {
            "resourceType": test_patient["resourceType"],
            "id": test_patient["id"],
            "meta": {"tag": [{"system": seed_tcga_cohort.PROVENANCE_SYSTEM, "code": seed_tcga_cohort.SYNTHETIC_TAG_CODE}]},
        }

        put_called = False
        def fake_request(method, path, body=None, max_retries=3):
            nonlocal put_called
            if method == "POST" and body and body.get("type") == "transaction":
                put_called = True
                return 200, {}, {"entry": [{"response": {"status": "200 OK"}}]}
            if method == "GET":
                return 200, {}, tagged_record
            return 404, {}, {}

        client.request = fake_request
        with redirect_stdout(io.StringIO()):
            counts = seed_tcga_cohort.run_apply(client, [test_patient])
        self.assertTrue(put_called)
        self.assertEqual(1, counts["Patient"])

    def test_empty_cohort_raises(self):
        """E-13: Empty patient cohort config exits with non-zero code and explicit error."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(json.dumps({"description": "empty", "patients": []}))
            tf_path = Path(tf.name)

        try:
            stderr_buf = io.StringIO()
            with redirect_stderr(stderr_buf):
                with self.assertRaises(SystemExit) as cm:
                    seed_tcga_cohort.load_cohort(tf_path)
                self.assertNotEqual(0, cm.exception.code)
            self.assertIn("Empty cohort configuration", stderr_buf.getvalue())
        finally:
            tf_path.unlink(missing_ok=True)

    def test_untrusted_origin_rejection(self):
        """E-10: SSRF attack URL fails with exit code 2 and explicit message."""
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            with self.assertRaises(SystemExit) as cm:
                seed_tcga_cohort.validate_origin("https://attacker-controlled-site.com/fhir")
            self.assertEqual(2, cm.exception.code)
        self.assertIn("Refusing to send credentials to untrusted API origin", stderr_buf.getvalue())

    def test_delete_removes_only_tagged_resources(self):
        """FR-10 / E-6: Deletes only tagged synthetic resources, skips non-tagged."""
        client = seed_tcga_cohort.FHIRClient("https://mock-fhir.azurehealthcareapis.com", token="mock-token")
        p1 = self.resources[0]
        p2 = self.resources[1]

        records = {
            f"{p1['resourceType']}/{p1['id']}": {
                "resourceType": p1["resourceType"], "id": p1["id"],
                "meta": {"tag": [{"code": seed_tcga_cohort.SYNTHETIC_TAG_CODE}]},
            },
            f"{p2['resourceType']}/{p2['id']}": {
                "resourceType": p2["resourceType"], "id": p2["id"],
                "meta": {"tag": [{"code": "clinical-record"}]},
            },
        }
        deleted = []

        def fake_request(method, path, body=None, max_retries=3):
            if method == "GET":
                if path in records:
                    return 200, {}, records[path]
                return 404, {}, {}
            if method == "DELETE":
                deleted.append(path)
                return 204, {}, {}
            return 200, {}, {}

        client.request = fake_request
        with redirect_stdout(io.StringIO()):
            del_count = seed_tcga_cohort.run_delete(client, [p1, p2])

        self.assertEqual(1, del_count)
        self.assertEqual([f"{p1['resourceType']}/{p1['id']}"], deleted)


if __name__ == "__main__":
    unittest.main()
