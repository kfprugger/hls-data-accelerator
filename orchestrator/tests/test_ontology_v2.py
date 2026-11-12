import base64
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "phase-4"))
from build_ontology_v2 import build_ontology_v2_parts  # noqa: E402


class OntologyV2BuilderTests(unittest.TestCase):
    def test_clinical_device_ontology_generates_v2_tmdl_parts(self):
        res = build_ontology_v2_parts(
            ontology_name="ClinicalDeviceOntology",
            sql_endpoint="test.datawarehouse.fabric.microsoft.com",
            sql_endpoint_id="11111111-2222-3333-4444-555555555555",
            include_fhir=True,
            include_dicom=True,
            include_telemetry=True,
            include_gold=False,
        )
        self.assertEqual(res["entityCount"], 9)
        self.assertEqual(res["tableCount"], 8)
        self.assertEqual(res["relationshipCount"], 7)
        self.assertEqual(res["goldEntityCount"], 0)
        paths = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in res["parts"]}
        self.assertIn("database.tmdl", paths)
        self.assertIn("compatibilityLevel: 1000000", paths["database.tmdl"])
        self.assertIn("model.tmdl", paths)
        self.assertIn("ref namespace default", paths["model.tmdl"])
        self.assertIn("expressions.tmdl", paths)
        self.assertIn('Sql.Database("test.datawarehouse.fabric.microsoft.com", "11111111-2222-3333-4444-555555555555")', paths["expressions.tmdl"])
        for ent in ("Patient", "Encounter", "Condition", "MedRequest", "Observation", "ImagingStudy", "Device", "DeviceAssoc", "DeviceTelemetry"):
            self.assertIn(f"entities/{ent}.tmdl", paths)
        self.assertIn("rules/HypoxemiaTelemetryRule.tmdl", paths)

    def test_device_payer_ontology_includes_17_entities_and_15_relationships(self):
        res = build_ontology_v2_parts(
            ontology_name="DevicePayerOntology",
            sql_endpoint="gold.datawarehouse.fabric.microsoft.com",
            sql_endpoint_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            include_fhir=True,
            include_dicom=True,
            include_telemetry=True,
            include_gold=True,
        )
        self.assertEqual(res["entityCount"], 17)
        self.assertEqual(res["tableCount"], 16)
        self.assertEqual(res["relationshipCount"], 15)
        self.assertEqual(res["goldEntityCount"], 8)
        paths = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in res["parts"]}
        for ent in ("Claim", "Payer", "Diagnosis", "PatientDiagnosis", "MedAdherence", "CareGap", "PatientRisk", "HighCostClaimant"):
            self.assertIn(f"entities/{ent}.tmdl", paths)
        self.assertIn("entityRelationship hasClaim", paths["entityRelationships.tmdl"])
        self.assertIn("entityRelationship hasCareGap", paths["entityRelationships.tmdl"])


if __name__ == "__main__":
    unittest.main()
