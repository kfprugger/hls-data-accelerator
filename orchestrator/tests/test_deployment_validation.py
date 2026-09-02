from __future__ import annotations

import base64
import json

import unittest

from shared.deployment_validation import _eventhub_consumption_check, _quality_report_binding_check, effective_validation_config, fabric_runtime_expected, feature_presence_checks


class DeploymentValidationTests(unittest.TestCase):
    def test_legacy_continuation_still_requires_fabric_runtime(self) -> None:
        self.assertTrue(
            fabric_runtime_expected(
                {
                    "skip_fabric": True,
                    "continue_from_instance_id": "prior-run",
                    "skip_activator": False,
                }
            )
        )

    def test_requested_features_fail_when_only_workspace_exists(self) -> None:
        resources = {
            "workspace": {"id": "workspace-id", "name": "med-test"},
            "azure": [],
            "fabric": [],
        }
        config = {
            "skip_fabric": False,
            "skip_hds_pipelines": True,
            "skip_data_agents": True,
            "skip_imaging": True,
            "skip_ontology": True,
            "skip_activator": False,
            "alert_email": "alerts@example.test",
            "skip_quality_measures": True,
            "skip_phase7": True,
        }

        checks = feature_presence_checks(resources, config)
        failed_names = {check["name"] for check in checks if check["status"] == "fail"}

        self.assertIn("Masimo Eventstream", failed_names)
        self.assertIn("Masimo Eventhouse", failed_names)
        self.assertIn("Masimo KQL database", failed_names)
        self.assertIn("Masimo KQL dashboard", failed_names)
        self.assertIn("Clinical alert Activator", failed_names)

    def test_disabled_features_do_not_create_false_failures(self) -> None:
        checks = feature_presence_checks(
            {"workspace": None, "azure": [], "fabric": []},
            {
                "skip_fabric": True,
                "skip_hds_pipelines": True,
                "skip_data_agents": True,
                "skip_imaging": True,
                "skip_ontology": True,
                "skip_activator": True,
                "skip_quality_measures": True,
                "skip_phase7": True,
            },
        )

        self.assertEqual(checks, [])

    def test_scaffolding_validates_definitions_without_runtime_or_emulators(self) -> None:
        config = {
            "scaffolding_only": True,
            "skip_fabric": False,
            "skip_hds_pipelines": True,
            "skip_data_agents": True,
            "skip_imaging": True,
            "skip_ontology": True,
            "skip_activator": True,
            "skip_quality_measures": True,
            "skip_phase7": False,
            "skip_payer_rti": False,
            "skip_ops_agent": True,
            "skip_graph_agent": True,
            "skip_payer_activator": True,
        }

        self.assertFalse(fabric_runtime_expected(config))
        checks = feature_presence_checks(
            {"workspace": {"id": "ws", "name": "med-test"}, "azure": [], "fabric": []},
            config,
        )
        names = {check["name"] for check in checks}
        self.assertIn("Masimo Eventstream", names)
        self.assertIn("HDS Bronze lakehouse", names)
        self.assertIn("Clinical foundation pipeline", names)
        self.assertNotIn("Payer claim emulator", names)


    def test_eventhub_validation_filters_and_requires_each_entity(self) -> None:
        captured: list[str] = []

        class Result:
            returncode = 0
            stderr = ""
            stdout = json.dumps({
                "value": [
                    {"name": {"value": "IncomingMessages"}, "timeseries": [{"data": [{"total": 10}]}]},
                    {"name": {"value": "OutgoingMessages"}, "timeseries": [{"data": [{"total": 10}]}]},
                ]
            })

        def az_run(args):
            captured.extend(args)
            return Result()

        result = _eventhub_consumption_check(
            {
                "azure": [
                    {
                        "name": "namespace",
                        "fullType": "Microsoft.EventHub/namespaces",
                        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.EventHub/namespaces/ns",
                    }
                ]
            },
            {"expected_subscription_id": "sub"},
            az_run,
            "claim-stream",
        )

        self.assertEqual(result["status"], "pass")
        self.assertIn("EntityName eq 'claim-stream'", captured)

    def test_quality_validation_requires_new_phase6_artifacts(self) -> None:
        checks = feature_presence_checks(
            {
                "workspace": {"id": "workspace-id"},
                "azure": [],
                "fabric": [
                    {"id": "legacy-report", "name": "healthcare1_msft_cma_report", "type": "Report"},
                    {"id": "legacy-model", "name": "healthcare1_msft_cma_semantic_model", "type": "SemanticModel"},
                ],
            },
            {
                "skip_fabric": True,
                "skip_hds_pipelines": True,
                "skip_data_agents": True,
                "skip_imaging": True,
                "skip_ontology": True,
                "skip_activator": True,
                "skip_quality_measures": False,
                "skip_phase7": True,
            },
        )

        failed_names = {check["name"] for check in checks if check["status"] == "fail"}
        self.assertIn("Population health quality report", failed_names)
        self.assertIn("Population health quality semantic model", failed_names)

    def test_quality_report_binding_targets_phase6_semantic_model(self) -> None:
        resources = {
            "workspace": {"id": "workspace-id"},
            "fabric": [
                {"id": "report-id", "name": "Population Health & Quality Dashboard", "type": "Report"},
                {"id": "model-id", "name": "Population Health & Quality Semantic Model", "type": "SemanticModel"},
            ],
        }
        pbir = {
            "datasetReference": {
                "byConnection": {"connectionString": "Data Source=powerbi://example;semanticmodelid=model-id"}
            }
        }

        class Client:
            def get_item_definition(self, workspace_id, report_id):
                self.workspace_id = workspace_id
                self.report_id = report_id
                return {
                    "parts": [
                        {
                            "path": "definition.pbir",
                            "payload": base64.b64encode(json.dumps(pbir).encode()).decode(),
                        }
                    ]
                }

        result = _quality_report_binding_check(resources, Client)

        self.assertEqual(result["status"], "pass")
        self.assertIn("semanticModel=model-id", result["detail"])

    def test_phase7_validation_excludes_unrelated_full_deployment_features(self) -> None:
        config = effective_validation_config({
            "phase7_only": True,
            "continue_from_instance_id": "prior-full-run",
            "skip_fabric": False,
            "skip_hds_pipelines": False,
            "skip_data_agents": False,
            "skip_imaging": False,
            "skip_ontology": False,
            "skip_activator": False,
            "skip_quality_measures": False,
            "skip_phase7": False,
            "skip_payer_rti": False,
            "skip_ops_agent": False,
            "skip_graph_agent": False,
            "skip_payer_activator": False,
            "payer_ops_email": "payer@example.test",
        })

        self.assertFalse(fabric_runtime_expected(config))
        checks = feature_presence_checks({"workspace": {"id": "ws"}, "azure": [], "fabric": []}, config)
        names = {check["name"] for check in checks}
        self.assertIn("Payer claim emulator", names)
        self.assertIn("Healthcare Graph Agent", names)
        self.assertNotIn("HDS Bronze lakehouse", names)
        self.assertNotIn("Imaging report", names)
        self.assertNotIn("Population health report", names)


if __name__ == "__main__":
    unittest.main()
