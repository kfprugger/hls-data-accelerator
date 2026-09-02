from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SYNTHEA_DIR = Path(__file__).resolve().parents[1]


def load_generate_cached_bundles():
    module_name = "generate_cached_bundles_care_resources_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, SYNTHEA_DIR / "generate_cached_bundles.py")
    if spec is None or spec.loader is None:
        raise AssertionError("could not load generate_cached_bundles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class GeneratedCareResourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_generate_cached_bundles()
        self.addCleanup(sys.modules.pop, "generate_cached_bundles_care_resources_under_test", None)

    def resources_by_type(self, bundle: dict) -> dict[str, list[dict]]:
        resources: dict[str, list[dict]] = {}
        for entry in bundle["entry"]:
            resource = entry["resource"]
            resources.setdefault(resource["resourceType"], []).append(resource)
        return resources

    def test_coverage_resource_links_patient_to_payer_with_active_period(self) -> None:
        payer = {
            "id": "payer-test",
            "name": "Test Health Plan",
            "type_code": "MCPOL",
            "type_display": "managed care policy",
        }

        coverage = self.generator.coverage_resource("coverage-1", "patient-1", payer)

        self.assertEqual("Coverage", coverage["resourceType"])
        self.assertEqual("coverage-1", coverage["id"])
        self.assertEqual("active", coverage["status"])
        self.assertEqual("urn:uuid:patient-1", coverage["beneficiary"]["reference"])
        self.assertEqual(
            [{"reference": "Organization/payer-test", "display": "Test Health Plan"}],
            coverage["payor"],
        )
        self.assertEqual("MCPOL", coverage["type"]["coding"][0]["code"])
        self.assertRegex(coverage["period"]["start"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(coverage["period"]["end"], r"^\d{4}-\d{2}-\d{2}$")

    def test_goal_resource_has_patient_subject_and_due_target(self) -> None:
        profile = {
            "text": "Improve medication adherence",
            "target": "Take prescribed medication as directed",
        }

        goal = self.generator.goal_resource("goal-1", "patient-1", profile)

        self.assertEqual("Goal", goal["resourceType"])
        self.assertEqual("goal-1", goal["id"])
        self.assertEqual("active", goal["lifecycleStatus"])
        self.assertEqual({"text": "Improve medication adherence"}, goal["description"])
        self.assertEqual("urn:uuid:patient-1", goal["subject"]["reference"])
        self.assertEqual("Take prescribed medication as directed", goal["target"][0]["measure"]["text"])
        self.assertRegex(goal["startDate"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(goal["target"][0]["dueDate"], r"^\d{4}-\d{2}-\d{2}$")

    def test_generated_bundle_contains_coverage_goal_and_care_plan_wired_to_patient_condition(self) -> None:
        _, first_bundle = self.generator.generate_patient(1)
        _, second_bundle = self.generator.generate_patient(1)
        self.assertEqual(first_bundle, second_bundle)

        resources = self.resources_by_type(first_bundle)
        patient = resources["Patient"][0]
        coverage = resources["Coverage"][0]
        goal = resources["Goal"][0]
        care_plan = resources["CarePlan"][0]
        condition = resources["Condition"][0]
        encounters = {encounter["id"] for encounter in resources["Encounter"]}

        self.assertEqual(f"urn:uuid:{patient['id']}", coverage["beneficiary"]["reference"])
        self.assertEqual("Organization/payer-medicaid", coverage["payor"][0]["reference"])
        self.assertEqual(f"urn:uuid:{patient['id']}", goal["subject"]["reference"])
        self.assertEqual(f"urn:uuid:{patient['id']}", care_plan["subject"]["reference"])
        self.assertIn(care_plan["encounter"]["reference"].removeprefix("urn:uuid:"), encounters)
        self.assertEqual([{"reference": f"urn:uuid:{condition['id']}"}], care_plan["addresses"])
        self.assertEqual([{"reference": f"urn:uuid:{goal['id']}"}], care_plan["goal"])
        self.assertEqual("Assessment and Plan of Treatment", care_plan["category"][0]["text"])


if __name__ == "__main__":
    unittest.main()
