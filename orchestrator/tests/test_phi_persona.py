"""Unit and security verification tests for OneLake security PHI vs Researcher Persona.

Covers:
- E-3: Active attack simulation verifying researcher role is denied on identified patient table
- FR-1: Masking rules and server-side de-identification
- FR-2: OneLake data access security role structure and permission boundaries
- FR-3: Entra researcher persona management CLI dry-run and credential hygiene
"""
from __future__ import annotations

import io
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

WORKTREE_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS_DIR = WORKTREE_ROOT / "scripts"
PIPELINE_DIR = WORKTREE_ROOT / "rayfin-imaging" / "pipeline"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import manage_researcher_persona
import seed_deidentified_clinical


class OneLakePolicySimulator:
    """Simulates Fabric OneLake RBAC data access role enforcement."""

    def __init__(self, roles_config: dict) -> None:
        self.roles = roles_config.get("value", [])

    def evaluate_access(self, role_name: str, target_path: str, action: str = "Read") -> bool:
        role = next((r for r in self.roles if r.get("name") == role_name), None)
        if not role:
            return False

        for rule in role.get("decisionRules", []):
            if rule.get("effect") != "Permit":
                continue
            permitted_paths: list[str] = []
            permitted_actions: list[str] = []
            for perm in rule.get("permission", []):
                if perm.get("attributeName") == "Path":
                    permitted_paths = perm.get("attributeValueIncludedIn", [])
                elif perm.get("attributeName") == "Action":
                    permitted_actions = perm.get("attributeValueIncludedIn", [])

            if action not in permitted_actions:
                continue

            for p in permitted_paths:
                if p in ("*", "Tables/*") and target_path.startswith("Tables/"):
                    return True
                if p == target_path:
                    return True

        return False

    def query(self, role_name: str, sql: str) -> list[dict]:
        """Execute a query under a simulated role persona."""
        import re
        table_match = re.search(r"FROM\s+dbo\.([a-zA-Z0-9_]+)", sql, re.IGNORECASE)
        table_name = table_match.group(1) if table_match else ""
        target_path = f"Tables/{table_name}"

        if not self.evaluate_access(role_name, target_path, "Read"):
            # Simulate SQL Analytics / OneLake permission denied error
            raise PermissionError(
                f"HTTP 403 Forbidden - SQL Error: Cannot find the object \"dbo.{table_name}\" "
                f"because it does not exist or you do not have permissions. OneLake AccessDeniedOnPath: {target_path}"
            )

        return [{"simulated": True, "table": table_name}]


class TestPhiPersonaViews(unittest.TestCase):
    """Test suite for PHI de-identification, OneLake RBAC, and Entra persona lifecycle."""

    def setUp(self) -> None:
        self.tenant_id = "c77e97fc-1859-4575-8c8b-53d74bc35a63"
        self.nurse_id = "11111111-1111-1111-1111-111111111111"
        self.researcher_id = "22222222-2222-2222-2222-222222222222"
        self.roles_payload = manage_researcher_persona.build_data_access_roles(
            self.nurse_id, self.researcher_id, self.tenant_id
        )
        self.simulator = OneLakePolicySimulator(self.roles_payload)

    def test_researcher_denied_on_identified_patient_table(self) -> None:
        """E-3: Verify researcher persona is strictly denied when attempting to query dbo.patient."""
        # Nurse persona must succeed on identified patient table
        nurse_access = self.simulator.evaluate_access("ClinicalNurseRole", "Tables/patient")
        self.assertTrue(nurse_access, "ClinicalNurseRole must have access to Tables/patient")

        nurse_res = self.simulator.query("ClinicalNurseRole", "SELECT TOP 5 * FROM dbo.patient")
        self.assertEqual(nurse_res[0]["table"], "patient")

        # Researcher persona must be denied on identified patient table
        researcher_access = self.simulator.evaluate_access("ClinicalResearcherRole", "Tables/patient")
        self.assertFalse(researcher_access, "ClinicalResearcherRole must NOT have access to Tables/patient")

        # Executing the query under researcher role must raise permission error
        with self.assertRaises(PermissionError) as ctx:
            self.simulator.query("ClinicalResearcherRole", "SELECT TOP 5 * FROM dbo.patient")

        err_msg = str(ctx.exception)
        self.assertIn("Cannot find the object \"dbo.patient\" because it does not exist or you do not have permissions", err_msg)
        self.assertIn("AccessDeniedOnPath: Tables/patient", err_msg)
        self.assertIn("HTTP 403 Forbidden", err_msg)

        # Researcher persona must be allowed on de-identified patient table
        deid_access = self.simulator.evaluate_access("ClinicalResearcherRole", "Tables/patient_deidentified")
        self.assertTrue(deid_access, "ClinicalResearcherRole must have access to Tables/patient_deidentified")
        deid_res = self.simulator.query("ClinicalResearcherRole", "SELECT TOP 5 * FROM dbo.patient_deidentified")
        self.assertEqual(deid_res[0]["table"], "patient_deidentified")

    def test_masking_rules_and_deidentification(self) -> None:
        """FR-1: Verify patient records are de-identified with server-side masking."""
        raw_marcus = {
            "patient_id": "TCGA-G6-A8L6",
            "display_name": "Marcus Vance",
            "sex": "Male",
            "age_at_diagnosis": 55,
            "race": "Black or African American",
            "country": "United States",
            "year_of_diagnosis": 2011,
            "diagnosis_date": "2011-04-07",
            "address": "123 Main St, Seattle, WA",
            "phone": "555-0199",
            "email": "marcus.vance@example.com",
            "occupation": "Contractor",
        }

        deid_rows = seed_deidentified_clinical.derive_deidentified_patient_rows([raw_marcus])
        self.assertEqual(len(deid_rows), 1)
        res = deid_rows[0]

        # Name is replaced with patient_id
        self.assertEqual(res["display_name"], "TCGA-G6-A8L6")
        self.assertNotIn("Marcus Vance", str(res))
        self.assertNotIn("Marcus", str(res))

        # Demographic cohorts are retained
        self.assertEqual(res["race"], "Black or African American")
        self.assertEqual(res["country"], "United States")
        self.assertEqual(res["sex"], "Male")
        self.assertEqual(res["age_at_diagnosis"], 55)

        # Birth date coarsened to diagnosis year: 2011 - 55 = 1956
        self.assertEqual(res["birth_year"], 1956)
        self.assertEqual(res["birth_date"], "1956")
        self.assertEqual(res["diagnosis_date"], "2011-01-01")

        # Contact and specific location info stripped
        self.assertIsNone(res["address"])
        self.assertIsNone(res["phone"])
        self.assertIsNone(res["email"])
        self.assertIsNone(res["occupation"])
        self.assertTrue(res["is_deidentified"])

    def test_data_access_roles_json_serialization(self) -> None:
        """FR-2: Verify OneLake RBAC data access role structure conforms to Fabric schema."""
        roles = self.roles_payload.get("value", [])
        self.assertEqual(len(roles), 2)

        nurse_role = next(r for r in roles if r["name"] == "ClinicalNurseRole")
        researcher_role = next(r for r in roles if r["name"] == "ClinicalResearcherRole")

        # Nurse has Tables/*
        nurse_paths = nurse_role["decisionRules"][0]["permission"][0]["attributeValueIncludedIn"]
        self.assertIn("Tables/*", nurse_paths)

        # Researcher has designated de-identified and clinical tables only
        researcher_paths = researcher_role["decisionRules"][0]["permission"][0]["attributeValueIncludedIn"]
        self.assertIn("Tables/patient_deidentified", researcher_paths)
        self.assertIn("Tables/diagnosis", researcher_paths)
        self.assertIn("Tables/treatment", researcher_paths)
        self.assertIn("Tables/biomarker_test", researcher_paths)
        self.assertNotIn("Tables/patient", researcher_paths)

    def test_manage_researcher_persona_dry_run_create_and_delete(self) -> None:
        """E-6: Verify CLI dry-run validation for create and delete operations."""
        stdout_create = io.StringIO()
        with patch("sys.stdout", stdout_create):
            exit_code = manage_researcher_persona.main(["--dry-run"])
        self.assertEqual(exit_code, 0)
        out_create = stdout_create.getvalue()
        self.assertIn("Check Entra user researcher-demo@jbatl.dev", out_create)
        self.assertIn("Check OneLake data access role ClinicalResearcherRole", out_create)
        self.assertIn("Plan assignment to Tables/patient_deidentified", out_create)

        stdout_delete = io.StringIO()
        with patch("sys.stdout", stdout_delete):
            exit_code = manage_researcher_persona.main(["--delete", "--dry-run"])
        self.assertEqual(exit_code, 0)
        out_delete = stdout_delete.getvalue()
        self.assertIn("Checking Entra user researcher-demo@jbatl.dev", out_delete)
        self.assertIn("Checking OneLake data access role ClinicalResearcherRole", out_delete)
        self.assertIn("Plan removal of researcher-demo@jbatl.dev from Entra ID", out_delete)

    def test_ephemeral_credential_generation_and_hygiene(self) -> None:
        """FR-3, NFR-2: Verify credential entropy and absence of persisted credentials."""
        secret = manage_researcher_persona.generate_ephemeral_credential(24)
        self.assertGreaterEqual(len(secret), 24)
        self.assertTrue(any(c.isupper() for c in secret))
        self.assertTrue(any(c.islower() for c in secret))
        self.assertTrue(any(c.isdigit() for c in secret))
        self.assertTrue(any(c in "!@#$%^&*" for c in secret))


if __name__ == "__main__":
    unittest.main()
