from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SYNTHEA_DIR = Path(__file__).resolve().parents[1]


class CapacityFabric:
    """Fabric fake whose workspace capacity reports the given states in order."""

    subscription = "sub"

    def __init__(self, *states):
        self.states = list(states)

    def request(self, method, url, body=None):
        return 200, {}, {"capacityId": "cap"}

    def items(self, url):
        if url.endswith("/lakehouses"):
            return [{"id": "lh", "displayName": "demo_bronze"}]
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return [{"id": "cap", "displayName": "F64", "state": state,
                 "azureResourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Fabric/capacities/f64"}]


class DemoEnrichmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(sys, "path", [str(SYNTHEA_DIR), *sys.path]):
            spec = importlib.util.spec_from_file_location("apply_demo_enrichment_under_test", SYNTHEA_DIR / "apply_demo_enrichment.py")
            cls.runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.runner)

    def test_all_patient_pages_receive_coverage_with_stable_ids_on_rerun(self):
        # Different page sizes/order must not change deterministic patient scenarios.
        records = {}
        base = "https://example.invalid/fhir"
        pages = {
            base + "/Patient?_count=1": {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient", "id": "a"}}],
                                        "link": [{"relation": "next", "url": "?cursor=second"}]},
            base + "/Patient?cursor=second": {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient", "id": "b"}}]},
        }

        class Fhir:
            def __init__(self):
                self.base = base

            def request(self, method, url, body=None):
                if method == "GET":
                    return 200, {}, pages[url]
                responses = []
                for entry in body["entry"]:
                    key = entry["request"]["url"]
                    responses.append({"response": {"status": "200 OK" if key in records else "201 Created"}})
                    records[key] = entry["resource"]
                return 200, {}, {"entry": responses}

        client = Fhir()
        with redirect_stdout(io.StringIO()):
            patients = self.runner.load_patients(client, page_size=1)
            self.runner.apply_fhir(client, patients, date(2026, 10, 5))
            first = dict(records)
            self.runner.apply_fhir(client, list(reversed(patients)), date(2026, 10, 5))
        self.assertEqual({"Patient/a", "Patient/b"}, {resource["beneficiary"]["reference"] for resource in records.values() if resource["resourceType"] == "Coverage"})
        self.assertEqual(first, records)

    def test_transaction_entry_failure_or_missing_response_stops_enrichment(self):
        class Fhir:
            base = "https://example.invalid/fhir"

            def __init__(self, response_status):
                self.response_status = response_status

            def request(self, method, url, body=None):
                entries = [{"response": {"status": "201 Created"}} for _ in body["entry"]]
                if self.response_status is None:
                    entries.pop()
                else:
                    entries[-1]["response"]["status"] = self.response_status
                return 200, {}, {"entry": entries}

        for status in (None, "400 Bad Request", "2000 Invalid"):
            with self.subTest(status=status), self.assertRaisesRegex(RuntimeError, "transaction 1 failed"):
                self.runner.apply_fhir(Fhir(status), [{"id": "a"}], date(2026, 10, 5))

    def test_empty_fhir_cannot_replace_existing_outreach_sources(self):
        class Fhir:
            base = "https://example.invalid/fhir"

            def request(self, method, url):
                return 200, {}, {"resourceType": "Bundle", "entry": []}

        with self.assertRaisesRegex(RuntimeError, "no Patients"):
            self.runner.load_patients(Fhir())

    def test_failed_capacity_resume_stops_with_cli_error_before_polling(self):
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="AuthorizationFailed")
        with patch.object(self.runner.subprocess, "run", return_value=failed), \
                patch.object(self.runner.time, "sleep") as sleep, redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(RuntimeError, "AuthorizationFailed"):
            self.runner.resolve_lakehouse(CapacityFabric("Inactive"), "ws", None, resume_capacity=True)
        sleep.assert_not_called()

    def test_no_capacity_resume_fails_fast_without_resuming(self):
        with patch.object(self.runner.subprocess, "run") as run, \
                self.assertRaisesRegex(RuntimeError, "active Fabric capacity"):
            self.runner.resolve_lakehouse(CapacityFabric("Inactive"), "ws", None, resume_capacity=False)
        run.assert_not_called()

    def test_resumed_capacity_is_polled_until_active(self):
        accepted = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(self.runner.subprocess, "run", return_value=accepted) as run, \
                patch.object(self.runner.time, "sleep"), redirect_stdout(io.StringIO()):
            lakehouse = self.runner.resolve_lakehouse(CapacityFabric("Inactive", "Inactive", "Active"), "ws", None,
                                                      resume_capacity=True)
        self.assertEqual("lh", lakehouse["id"])
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
