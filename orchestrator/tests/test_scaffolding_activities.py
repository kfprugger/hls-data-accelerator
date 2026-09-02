from __future__ import annotations

import unittest
from unittest.mock import patch

from activities import deploy_azure_infra, deploy_fhir, deploy_payer_rti
from function_app import _effective_deployment_config
from shared.models import DeploymentConfig


class FakeAzureClient:
    def __init__(self) -> None:
        self.deployments: list[str] = []
        self.deployment_parameters: dict[str, dict] = {}
        self.builds: list[str] = []
        self.waits: list[str] = []

    def resolve_security_group_id(self, _name: str) -> str:
        return "group-id"

    def ensure_resource_group(self, *_args, **_kwargs) -> None:
        return None

    def deploy_bicep(self, *, deployment_name: str, **_kwargs):
        self.deployments.append(deployment_name)
        self.deployment_parameters[deployment_name] = _kwargs.get("parameters", {})
        if deployment_name == "infra":
            return {
                "acrName": "scaffoldacr",
                "eventHubNamespace": "scaffold-eh",
                "eventHubName": "telemetry-stream",
                "storageAccountName": "scaffoldstorage",
            }
        if deployment_name == "fhir-infra":
            return {
                "fhirServiceUrl": "https://fhir.example.test",
                "storageAccountName": "fhirscaffold",
                "managedIdentityId": "fhir-mi",
            }
        return {}

    def build_container_image(self, *, image_name: str, **_kwargs) -> str:
        self.builds.append(image_name)
        return image_name

    def wait_for_aci_job(self, *, container_group_name: str, **_kwargs):
        self.waits.append(container_group_name)
        return {"state": "Succeeded", "exit_code": 0, "duration_seconds": 1.0}


class ScaffoldingActivityTests(unittest.TestCase):
    def test_durable_model_preserves_zero_data_flags(self) -> None:
        config = DeploymentConfig(
            fabric_workspace_name="scaffold-test",
            scaffolding_only=True,
            skip_synthea=True,
            skip_hds_pipelines=True,
            skip_hds_source=False,
        ).model_dump()

        self.assertTrue(config["scaffolding_only"])
        self.assertTrue(config["skip_synthea"])
        self.assertTrue(config["skip_hds_pipelines"])
        self.assertFalse(config["skip_hds_source"])

    def test_durable_model_defaults_reseed_off_and_rejects_reuse_combination(self) -> None:
        config = DeploymentConfig(fabric_workspace_name="reseed-test")

        self.assertFalse(config.reseed_data)
        cached = DeploymentConfig(
            fabric_workspace_name="reseed-test", patient_count=250, use_cached_synthea=True
        )
        self.assertEqual(cached.patient_count, 100)
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            DeploymentConfig(
                fabric_workspace_name="reseed-test",
                reuse_patients=True,
                reseed_data=True,
            )

    def test_durable_reseed_forces_all_fhir_data_work(self) -> None:
        config = _effective_deployment_config({
            "reseed_data": True,
            "reuse_patients": False,
            "skip_fhir": True,
            "skip_synthea": True,
            "skip_device_assoc": True,
            "skip_fhir_export": True,
            "skip_hds_pipelines": True,
        })

        self.assertTrue(config["reseed_data"])
        for field in (
            "reuse_patients",
            "skip_fhir",
            "skip_synthea",
            "skip_device_assoc",
            "skip_fhir_export",
            "skip_hds_pipelines",
        ):
            self.assertFalse(config[field], field)

    def test_durable_normalization_disables_data_work_but_keeps_hds_source(self) -> None:
        config = _effective_deployment_config({"scaffolding_only": True})

        for field in (
            "skip_synthea",
            "skip_device_assoc",
            "skip_dicom",
            "skip_fhir_export",
            "skip_rti_phase2",
            "skip_hds_pipelines",
            "skip_data_agents",
            "skip_imaging",
            "skip_ontology",
            "skip_activator",
            "skip_quality_measures",
            "skip_payer_activator",
        ):
            self.assertTrue(config[field], field)
        self.assertFalse(config.get("skip_hds_source", False))
        self.assertFalse(config.get("skip_fhir", False))
        self.assertFalse(config.get("skip_fabric", False))

    def test_existing_telemetry_emulator_is_stopped(self) -> None:
        calls: list[list[str]] = []

        class Result:
            returncode = 0
            stderr = ""

            def __init__(self, stdout: str = "") -> None:
                self.stdout = stdout

        def runner(args, **_kwargs):
            calls.append(args)
            return Result("Running\n") if args[2] == "show" else Result()

        stopped = deploy_azure_infra._stop_container_if_present(
            "rg-scaffold", "masimo-emulator-grp", runner
        )

        self.assertTrue(stopped)
        self.assertEqual([args[2] for args in calls], ["show", "stop"])


    def test_azure_activity_omits_telemetry_emulator(self) -> None:
        client = FakeAzureClient()
        config = {
            "resource_group_name": "rg-scaffold",
            "location": "eastus",
            "fabric_workspace_name": "scaffold-test",
            "scaffolding_only": True,
        }

        with (
            patch.object(deploy_azure_infra, "AzureClient", return_value=client),
            patch.object(deploy_azure_infra, "_stop_container_if_present", return_value=False) as stop,
        ):
            result = deploy_azure_infra.run(config)

        self.assertEqual(stop.call_count, 5)

        self.assertEqual(client.deployments, ["infra"])
        self.assertEqual(client.builds, [])
        self.assertFalse(any(key.startswith("emulator_") for key in result["resources"]))

    def test_fhir_activity_deploys_infrastructure_without_jobs(self) -> None:
        client = FakeAzureClient()
        config = {
            "resource_group_name": "rg-scaffold",
            "location": "eastus",
            "scaffolding_only": True,
        }

        with patch.object(deploy_fhir, "AzureClient", return_value=client):
            result = deploy_fhir.run(config, {"acr_name": "scaffoldacr"})

        self.assertEqual(client.deployments, ["fhir-infra"])
        self.assertEqual(client.builds, [])
        self.assertEqual(client.waits, [])
        self.assertEqual(result["resources"]["synthea_state"], "Skipped")
        self.assertEqual(result["resources"]["loader_state"], "Skipped")

    def test_fhir_activity_passes_reseed_flag_to_loader_job(self) -> None:
        client = FakeAzureClient()
        config = {
            "resource_group_name": "rg-reseed",
            "location": "eastus",
            "reseed_data": True,
        }

        with patch.object(deploy_fhir, "AzureClient", return_value=client):
            deploy_fhir.run(config, {"acr_name": "reseedacr"})

        self.assertTrue(client.deployment_parameters["fhir-loader-job"]["reseedData"])

    def test_payer_activity_omits_claim_emulator_only(self) -> None:
        captured: list[str] = []

        def run_powershell(args, **_kwargs) -> int:
            captured.extend(args)
            return 0

        config = {
            "fabric_workspace_name": "scaffold-test",
            "resource_group_name": "rg-scaffold",
            "scaffolding_only": True,
        }
        with patch.object(deploy_payer_rti, "_run_powershell", side_effect=run_powershell):
            deploy_payer_rti.run(config, {})

        command = " ".join(captured)
        self.assertIn("-SkipClaimEmulator", command)
        self.assertNotIn("-SkipPayerRti", command)


        self.assertIn("-SkipClaimEmulator", command)
        self.assertIn("-SkipSnapshotMaterialization", command)
        self.assertNotIn("-SkipPayerRti", command)
