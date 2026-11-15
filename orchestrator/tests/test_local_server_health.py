from __future__ import annotations

import asyncio
import contextlib
import inspect
import os

import importlib
import io
import json
import logging
import sys
import shutil
import threading
import types
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

_MISSING = object()


class LocalServerHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orchestrator_dir = str(Path(__file__).resolve().parents[1])
        self._inserted_path = False
        if self._orchestrator_dir not in sys.path:
            sys.path.insert(0, self._orchestrator_dir)
            self._inserted_path = True
        self._saved_modules = {
            name: sys.modules.get(name, _MISSING)
            for name in ("local_server", "shared.database")
        }
        self._saved_shared_database_attr = _MISSING
        shared_pkg = sys.modules.get("shared")
        if shared_pkg is not None and hasattr(shared_pkg, "database"):
            self._saved_shared_database_attr = getattr(shared_pkg, "database")
        self._saved_excepthook = sys.excepthook
        self._saved_threading_excepthook = threading.excepthook
        self.addCleanup(self._cleanup_imports)

        self.local_server = self._import_local_server()

    def _cleanup_imports(self) -> None:
        sys.excepthook = self._saved_excepthook
        threading.excepthook = self._saved_threading_excepthook
        for module_name, module in self._saved_modules.items():
            if module is _MISSING:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = module
        shared_pkg = sys.modules.get("shared")
        if shared_pkg is not None:
            if self._saved_shared_database_attr is _MISSING:
                if getattr(shared_pkg, "database", None) is self._fake_database:
                    delattr(shared_pkg, "database")
            else:
                setattr(shared_pkg, "database", self._saved_shared_database_attr)
        if self._inserted_path and self._orchestrator_dir in sys.path:
            sys.path.remove(self._orchestrator_dir)

    def _fake_database_module(self) -> types.ModuleType:
        class FakeConnection:
            def execute(self, query: str):
                if query != "SELECT 1":
                    raise AssertionError(f"unexpected liveness query: {query}")
                return self

            def fetchone(self):
                return (1,)

        module = types.ModuleType("shared.database")
        module.save_deployment = lambda *args, **kwargs: None
        module.get_deployment = lambda *args, **kwargs: None
        module.list_deployments = lambda *args, **kwargs: []
        module.delete_deployment = lambda *args, **kwargs: False
        module.get_db = lambda *args, **kwargs: FakeConnection()
        module.clear_all_deployments = lambda *args, **kwargs: 0
        module.mark_stale_as_terminated = lambda *args, **kwargs: None
        module.migrate_from_json = lambda *args, **kwargs: None
        module.get_locks = lambda *args, **kwargs: []
        module.set_lock = lambda *args, **kwargs: None
        module.remove_lock = lambda *args, **kwargs: None
        module.get_form_history = lambda *args, **kwargs: []
        module.add_form_history = lambda *args, **kwargs: None
        module.get_dismissed_teardowns = lambda *args, **kwargs: []
        module.dismiss_teardown = lambda *args, **kwargs: None
        module.record_deployment_form_history = lambda *args, **kwargs: 0
        module.backfill_form_history_from_deployments = lambda *args, **kwargs: 0
        module.reconcile_from_state_tracking_dir = lambda *args, **kwargs: []
        module.import_target_history_from_shared_storage = lambda *args, **kwargs: {
            "importedDeployments": 0, "importedFormHistory": 0, "reconstructedLedgers": 0
        }
        return module

    def _import_local_server(self):
        sys.modules.pop("local_server", None)
        self._fake_database = self._fake_database_module()
        sys.modules["shared.database"] = self._fake_database
        original_path_open = Path.open

        def path_open_without_crash_dump(path: Path, *args, **kwargs):
            if path.name == "backend-crash-dump.log":
                return io.StringIO()
            return original_path_open(path, *args, **kwargs)

        with (
            patch("logging.FileHandler", return_value=logging.NullHandler()),
            patch("pathlib.Path.open", new=path_open_without_crash_dump),
            patch("faulthandler.enable"),
            patch("faulthandler.register"),
            patch("signal.signal"),
            patch("atexit.register"),
        ):
            return importlib.import_module("local_server")

    def _get_route_endpoint(self, path: str):
        for route in self.local_server.app.routes:
            if getattr(route, "path", None) == path and "GET" in getattr(route, "methods", set()):
                return route.endpoint
        self.fail(f"GET {path} route is not registered")

    def _call_get_route(self, path: str, **query):
        endpoint = self._get_route_endpoint(path)
        if inspect.iscoroutinefunction(endpoint):
            return asyncio.run(endpoint(**query))
        return endpoint(**query)

    def _forbid_readiness_checks(self) -> None:
        def forbidden(*args, **kwargs):
            raise AssertionError("liveness endpoints must not call auth or capacity scans")

        async def forbidden_async(*args, **kwargs):
            forbidden(*args, **kwargs)

        self.local_server._get_auth_context_sync = forbidden
        self.local_server._list_capacities_sync = forbidden
        self.local_server.list_capacities = forbidden_async

    def assert_liveness_payload(self, payload: dict[str, object]) -> None:
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("backend"), "online")
        self.assertEqual(payload.get("database"), "ok")
        checked_at = payload.get("checkedAt")
        self.assertIsInstance(checked_at, str)
        datetime.fromisoformat(checked_at.replace("Z", "+00:00"))

    def test_live_endpoint_is_cheap_and_reports_backend_database_liveness(self) -> None:
        self._forbid_readiness_checks()

        payload = self._call_get_route("/api/live")

        self.assert_liveness_payload(payload)

    def test_health_default_uses_cheap_liveness_contract(self) -> None:
        self._forbid_readiness_checks()

        payload = self._call_get_route("/api/health")

        self.assert_liveness_payload(payload)
        self.assertNotIn("auth", payload)
        self.assertNotIn("capacities", payload)

    def test_health_deep_reports_auth_and_capacity_readiness(self) -> None:
        auth_context = {"ready": True, "user": "operator@example.com", "issues": []}
        capacities = [
            {"name": "cap-active", "state": "Active"},
            {"name": "cap-paused", "state": "Paused"},
        ]

        def fake_auth_context() -> dict[str, object]:
            return auth_context

        def fake_list_capacities_sync(subscription_id: str = "", force: bool = False):
            return capacities

        async def fake_list_capacities(subscription_id: str = "", force: bool = False):
            return capacities

        self.local_server._get_auth_context_sync = fake_auth_context
        self.local_server._list_capacities_sync = fake_list_capacities_sync
        self.local_server.list_capacities = fake_list_capacities

        payload = self._call_get_route("/api/health", deep=True)

        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("backend"), "online")
        self.assertEqual(payload.get("database"), "ok")
        self.assertEqual(payload.get("auth"), auth_context)
        self.assertEqual(
            payload.get("capacities"),
            {"total": 2, "active": 1, "items": capacities},
        )
        self.assertIsInstance(payload.get("checkedAt"), str)

    def test_auth_probe_imports_isolated_az_context_and_aligns_context_fields(self) -> None:
        commands: list[list[str]] = []

        def fake_az_run(args: list[str], **kwargs):
            commands.append(args)
            if args[0] == "az" and args[1] == "version":
                return types.SimpleNamespace(returncode=0, stdout="{}", stderr="")
            if args[0] == "az" and args[1:3] == ["account", "show"]:
                return types.SimpleNamespace(
                    returncode=0,
                    stdout='{"user":"cli-user","subscriptionName":"Production","subscriptionId":"SUB-123","tenantId":"TENANT-456"}',
                    stderr="",
                )
            if args[0] == "pwsh":
                return types.SimpleNamespace(
                    returncode=0,
                    stdout='{"installed":true,"loggedIn":true,"user":"ps-user","subscriptionName":"Production","subscriptionId":"sub-123","tenantId":"tenant-456","error":""}',
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {args!r}")

        with patch.dict(os.environ, {"AZURE_CONFIG_DIR": "/tmp/isolated-azure"}), patch.object(
            self.local_server, "_az_run", side_effect=fake_az_run
        ):
            result = self.local_server._get_auth_context_sync()

        pwsh_command = next(command[-1] for command in commands if command[0] == "pwsh")
        import_path = "Join-Path $env:AZURE_CONFIG_DIR 'azps-context.json'"
        import_command = "Import-AzContext -Path $isolatedContext -ErrorAction Stop | Out-Null"
        get_context = "$ctx = Get-AzContext -ErrorAction Stop"
        self.assertIn(import_path, pwsh_command)
        self.assertIn(import_command, pwsh_command)
        self.assertIn(get_context, pwsh_command)
        self.assertLess(pwsh_command.index(import_command), pwsh_command.index(get_context))
        self.assertTrue(result["ready"])
        self.assertEqual(result["aligned"], {"subscription": True, "tenant": True})


    def test_auth_probe_delegates_az_powershell_when_only_azure_cli_is_logged_in(self) -> None:
        def fake_az_run(args: list[str], **kwargs):
            if args[0] == "az" and args[1] == "version":
                return types.SimpleNamespace(returncode=0, stdout="{}", stderr="")
            if args[0] == "az" and args[1:3] == ["account", "show"]:
                return types.SimpleNamespace(
                    returncode=0,
                    stdout='{"user":"cli-user@example.com","subscriptionName":"Production","subscriptionId":"SUB-123","tenantId":"TENANT-456"}',
                    stderr="",
                )
            if args[0] == "pwsh":
                return types.SimpleNamespace(
                    returncode=0,
                    stdout='{"installed":true,"loggedIn":false,"user":"","subscriptionName":"","subscriptionId":"","tenantId":"","error":"No active Az context"}',
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {args!r}")

        with patch.object(self.local_server, "_az_run", side_effect=fake_az_run):
            result = self.local_server._get_auth_context_sync()

        self.assertTrue(result["ready"])
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["pwsh"]["loggedIn"])
        self.assertTrue(result["pwsh"].get("delegatedToCli"))
        self.assertEqual(result["pwsh"]["user"], "cli-user@example.com")
        self.assertEqual(result["aligned"], {"subscription": True, "tenant": True})
    def test_phase_log_matching_accepts_ui_cards_for_backend_phase_names(self) -> None:
        matching_cases = [
            (
                "RTI enrichment card",
                "Phase 2: Fabric RTI Enrichment (auto)",
                "2c. Active Patient Telemetry: Fabric RTI Enrichment",
            ),
            (
                "HDS source deployment card",
                "Phase 3: HDS Source Deployment",
                "2b. Active Patient Telemetry: HDS Source Deployment",
            ),
            (
                "DICOM shortcut and HDS pipelines card",
                "Phase 3: DICOM Shortcut + HDS Pipelines (auto)",
                "3a. HDS Bridge + Row Gates: DICOM Shortcut + HDS Pipelines",
            ),
        ]

        for name, entry_phase, requested_phase in matching_cases:
            with self.subTest(name=name):
                self.assertTrue(
                    self.local_server._phase_log_matches(entry_phase, requested_phase),
                    f"{entry_phase!r} should match {requested_phase!r}",
                )

    def test_phase_log_matching_rejects_unrelated_backend_phase_names(self) -> None:
        self.assertFalse(
            self.local_server._phase_log_matches(
                "Phase 2: Fabric RTI Enrichment (auto)",
                "2b. Active Patient Telemetry: HDS Source Deployment",
            )
        )


    def test_deploy_request_requires_explicit_nonempty_azure_targets(self) -> None:
        with self.assertRaises(ValueError):
            self.local_server.DeployRequest(fabric_workspace_name="test")
        for invalid in ("", "not-a-uuid", "00000000-0000-0000-0000-000000000000"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.local_server.DeployRequest(
                    expected_tenant_id=invalid,
                    expected_subscription_id="22222222-2222-2222-2222-222222222222",
                )

    def test_local_deploy_request_defaults_reseed_off_and_rejects_reuse(self) -> None:
        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test")

        self.assertFalse(request.reseed_data)
        cached = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test", patient_count=250, use_cached_synthea=True)
        self.assertEqual(cached.patient_count, 100)
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test",
            reuse_patients=True,
            reseed_data=True,)

    def test_local_reseed_overrides_resume_and_skip_flags(self) -> None:
        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test",
        reseed_data=True,
        skip_fhir=True,
        skip_synthea=True,
        skip_device_assoc=True,
        skip_fhir_export=True,
        skip_hds_pipelines=True,)
        request.reuse_patients = True  # Simulate a live auto-resume mutation.

        self.local_server._apply_reseed_data(request)

        self.assertTrue(request.reseed_data)
        for field in (
            "reuse_patients",
            "skip_fhir",
            "skip_synthea",
            "skip_device_assoc",
            "skip_fhir_export",
            "skip_hds_pipelines",
        ):
            self.assertFalse(getattr(request, field), field)

    def test_completed_deployment_is_reseed_target_but_teardown_is_not(self) -> None:
        completed = {
            "instanceId": "completed-deploy",
            "name": "deploy_all_orchestrator",
            "runtimeStatus": "Completed",
            "createdTime": "2026-08-04T10:00:00Z",
            "customStatus": {
                "status": "succeeded",
                "workspaceName": "med-existing",
                "resourceGroupName": "rg-med-existing",
                "deployConfig": {"patient_count": 100},
            },
        }
        teardown = {
            "instanceId": "completed-teardown",
            "name": "teardown_orchestrator",
            "runtimeStatus": "Completed",
            "createdTime": "2026-08-04T11:00:00Z",
            "customStatus": {
                "status": "succeeded",
                "workspaceName": "med-existing",
                "resourceGroupName": "rg-med-existing",
            },
        }
        self.local_server.deployments.update({"deploy": completed, "teardown": teardown})

        result = asyncio.run(
            self.local_server.check_existing_deployment(workspace_name="med-existing")
        )

        self.assertEqual(result["instanceId"], "completed-deploy")
        self.local_server.deployments.clear()
        self.local_server.deployments["teardown"] = teardown
        self.assertIsNone(
            asyncio.run(self.local_server.check_existing_deployment(workspace_name="med-existing"))
        )

    def test_continuation_reuses_rti_without_disabling_downstream_features(self) -> None:
        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test",
        resource_group_name="rg-med-test",)
        prior = {
            "instanceId": "prior-run",
            "output": {
                "phases": [
                    {"phase": "Phase 2: Fabric RTI", "status": "succeeded"},
                ]
            },
        }

        with (
            patch.object(self.local_server, "_cloud_state_sync", return_value={"workspace": {"exists": True}, "resourceGroup": {"exists": True}}),
            patch.object(self.local_server, "_live_resume_prerequisites", return_value={}),
            patch.object(self.local_server, "_phase_live_prerequisites_ok", return_value=(True, "verified")),
            patch.object(self.local_server, "_phase_has_blocking_logs", return_value=False),
        ):
            applied = self.local_server._apply_success_skips_from_deployment(request, prior)

        self.assertTrue(applied)
        self.assertTrue(request.reuse_fabric_rti)
        self.assertFalse(request.skip_fabric)
        self.assertFalse(request.skip_activator)
        self.assertFalse(request.skip_phase7)
        self.assertFalse(request.skip_payer_rti)
        self.assertFalse(request.skip_ops_agent)
        self.assertFalse(request.skip_graph_agent)

    def _live_continuation(self, cloud_state: dict, counts: dict):
        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test", resource_group_name="rg-med-test")
        with (
            patch.object(self.local_server, "_cloud_state_sync", return_value=cloud_state),
            patch.object(self.local_server, "_live_resume_prerequisites", return_value={"fhirCounts": counts}),
        ):
            self.local_server._apply_live_continuation_skips(request, {"instanceId": "prior-run"})
        return request

    def test_live_continuation_refuses_unverified_estate_instead_of_reseeding(self) -> None:
        # A failed probe once read a 100-patient estate as empty, which would have loaded new Synthea patients.
        verified = {"patients": 100, "devices": 100, "exportedFiles": 0, "dicomStudies": 202, "countsVerified": True}
        rg_found = {"workspace": {"exists": True}, "resourceGroup": {"exists": True}}
        rg_unknown = {"workspace": {"exists": True}, "resourceGroup": {"exists": None, "status": "unreachable"}}
        with self.assertRaises(self.local_server.HTTPException) as unknown_rg:
            self._live_continuation(rg_unknown, verified)
        self.assertEqual(unknown_rg.exception.status_code, 503)
        with self.assertRaises(self.local_server.HTTPException) as unverified_counts:
            self._live_continuation(rg_found, {"patients": 0, "devices": 0, "countsVerified": False})
        self.assertEqual(unverified_counts.exception.status_code, 503)
        reused = self._live_continuation(rg_found, verified)
        self.assertTrue(reused.reuse_patients)
        self.assertTrue(reused.skip_synthea)
        self.assertTrue(reused.skip_dicom)

    def test_failed_resource_group_probe_is_unknown_not_deleted(self) -> None:
        failed = types.SimpleNamespace(returncode=1, stdout="", stderr="connection reset")
        with patch.object(self.local_server, "_az_run", return_value=failed):
            state = self.local_server._cloud_state_sync("", "rg-med-test")
        self.assertIsNone(state["resourceGroup"]["exists"])
        self.assertEqual(state["resourceGroup"]["status"], "unreachable")

    def _ontology_resume(self, phases: list[dict]):
        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test",
        resource_group_name="rg-med-test",)
        prior = {"instanceId": "prior-run", "output": {"phases": phases}}
        with (
            patch.object(self.local_server, "_cloud_state_sync", return_value={"workspace": {"exists": True}, "resourceGroup": {"exists": True}}),
            patch.object(self.local_server, "_live_resume_prerequisites", return_value={}),
            patch.object(self.local_server, "_phase_live_prerequisites_ok", return_value=(True, "verified")),
            patch.object(self.local_server, "_phase_has_blocking_logs", return_value=False),
        ):
            self.local_server._apply_success_skips_from_deployment(request, prior)
        return request

    def test_resume_reruns_ontology_unless_every_ontology_step_and_phase_6_succeeded(self) -> None:
        phase_4 = [
            {"phase": "PHASE 4: ONTOLOGY", "status": "succeeded"},
            {"phase": "Phase 4: Ontology Deployment", "status": "succeeded"},
            {"phase": "Phase 4: Ontology-Aware Data Agents", "status": "succeeded"},
        ]
        phase_6 = {"phase": "Phase 6: CMS Quality Measures", "status": "succeeded"}
        agents_failed = phase_4[:2] + [{"phase": "Phase 4: Ontology-Aware Data Agents", "status": "failed"}]

        self.assertFalse(self._ontology_resume(agents_failed + [phase_6]).skip_ontology)
        # DevicePayerOntology deploys in Phase 6, so Phase 4 alone is not the whole ontology.
        self.assertFalse(self._ontology_resume(phase_4).skip_ontology)
        complete = self._ontology_resume(phase_4 + [phase_6])
        self.assertTrue(complete.skip_ontology)
        self.assertTrue(complete.skip_quality_measures)

    def test_auto_resume_uses_only_the_newest_deployment_for_the_target(self) -> None:
        def record(instance_id: str, status: str, created: str) -> dict:
            return {"instanceId": instance_id, "runtimeStatus": status, "createdTime": created,
                    "customStatus": {"workspaceName": "med-test", "resourceGroupName": "rg-med-test"}}

        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test", resource_group_name="rg-med-test")
        self.local_server.deployments.clear()
        self.local_server.deployments["older-failed"] = record("older-failed", "Failed", "2026-10-05T13:42:27Z")
        self.local_server.deployments["newer-completed"] = record("newer-completed", "Completed", "2026-10-05T14:19:12Z")
        with patch.object(self.local_server, "_apply_success_skips_from_deployment") as resume:
            self.local_server._apply_prior_success_skips(request)
            resume.assert_not_called()

            self.local_server.deployments["newest-failed"] = record("newest-failed", "Failed", "2026-10-05T23:00:00Z")
            self.local_server._apply_prior_success_skips(request)
            resume.assert_called_once_with(request, self.local_server.deployments["newest-failed"])
        self.local_server.deployments.clear()

    def test_scaffolding_only_disables_all_data_producers(self) -> None:
        request = self.local_server.DeployRequest(expected_tenant_id="11111111-1111-1111-1111-111111111111", expected_subscription_id="22222222-2222-2222-2222-222222222222", fabric_workspace_name="med-test",
        resource_group_name="rg-med-test",
        scaffolding_only=True,)

        self.local_server._apply_scaffolding_only(request)

        self.assertTrue(request.skip_synthea)
        self.assertTrue(request.skip_device_assoc)
        self.assertTrue(request.skip_dicom)
        self.assertTrue(request.skip_fhir_export)
        self.assertTrue(request.skip_hds_pipelines)
        self.assertTrue(request.skip_rti_phase2)
        self.assertTrue(request.skip_payer_activator)
        self.assertFalse(request.skip_fhir)
        self.assertFalse(request.skip_fabric)
        self.assertFalse(request.skip_phase7)
        self.assertFalse(request.skip_payer_rti)

    def test_terminal_substep_rejects_replayed_progress_timing(self) -> None:
        existing = {
            "status": "succeeded",
            "detail": "42 files",
            "attempt": 1,
            "emittedAt": "2026-08-02T14:00:02Z",
            "finishedAt": "2026-08-02T14:00:02Z",
            "durationSeconds": 2.0,
        }
        replayed = {
            "status": "running",
            "detail": "Streaming",
            "attempt": 1,
            "emittedAt": "2026-08-02T14:00:00Z",
            "durationSeconds": 0.5,
        }

        merged = self.local_server._merge_substep_state(existing, replayed)

        self.assertFalse(merged)
        self.assertEqual(existing["status"], "succeeded")
        self.assertEqual(existing["detail"], "42 files")
        self.assertEqual(existing["durationSeconds"], 2.0)
        self.assertEqual(existing["finishedAt"], "2026-08-02T14:00:02Z")

    def test_new_attempt_reopens_terminal_substep(self) -> None:
        existing = {
            "status": "failed",
            "attempt": 1,
            "finishedAt": "2026-08-02T14:00:02Z",
            "duration": "2.0 sec",
            "durationSeconds": 2.0,
        }
        retry = {
            "status": "running",
            "attempt": 2,
            "startedAt": "2026-08-02T14:01:00Z",
            "durationSeconds": 0.0,
        }

        merged = self.local_server._merge_substep_state(existing, retry)

        self.assertTrue(merged)
        self.assertEqual(existing["status"], "running")
        self.assertEqual(existing["attempt"], 2)
        self.assertNotIn("finishedAt", existing)
        self.assertNotIn("duration", existing)
        self.assertEqual(existing["durationSeconds"], 0.0)

    def test_successful_revalidation_clears_stale_completed_failure_detail(self) -> None:
        deployment = {
            "runtimeStatus": "Completed",
            "customStatus": {
                "status": "succeeded",
                "detail": "Live validation attempt 2/3 failed: claim-stream had no messages",
            },
            "output": {
                "status": "succeeded",
                "phases": [
                    {
                        "phase": "PHASE 6: CMS QUALITY MEASURES",
                        "status": "warning",
                        "detail": "Deploy-All.ps1 exited with code 1",
                        "subSteps": [{"name": "Clinical Pipeline", "status": "running"}],
                    }
                ],
            },
        }
        validation = {
            "passed": True,
            "checkedAt": "2026-08-04T10:03:52Z",
            "checks": [
                {"name": "claim-stream", "status": "pass"},
                {"name": "quality model", "status": "pass"},
            ],
        }

        changed = self.local_server._reconcile_deployment_completion_from_validation(
            "deployment-id", deployment, validation
        )

        self.assertTrue(changed)
        self.assertEqual(deployment["customStatus"]["detail"], "Post-deployment validation passed: 2 checks.")
        self.assertEqual(deployment["customStatus"]["validatedAt"], "2026-08-04T10:03:52Z")
        phase = deployment["output"]["phases"][0]
        self.assertEqual(phase["status"], "succeeded")
        self.assertEqual(phase["subSteps"][0]["status"], "succeeded")
        self.assertEqual(phase["detail"], "Post-deployment validation passed after repair.")

    def test_teardown_batch_with_an_unpinned_job_starts_nothing(self) -> None:
        from fastapi import HTTPException

        started: list[str] = []

        def record_task(coro, name):
            started.append(name)
            coro.close()

        self.local_server._create_logged_task = record_task
        before = dict(self.local_server.deployments)
        request = self.local_server.TeardownBatchRequest(jobs=[
            self.local_server.TeardownRequest(resource_group_name="rg-a", subscription_id="sub-a"),
            self.local_server.TeardownRequest(resource_group_name="rg-b"),
        ])

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(self.local_server.start_teardown_batch(request))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(started, [])
        self.assertEqual(self.local_server.deployments, before)

    def test_unpinned_teardown_record_is_not_reconciled(self) -> None:
        record = {
            "runtimeStatus": "Running",
            "customStatus": {"runType": "teardown", "resourceGroupName": "rg-a", "workspaceName": "ws-a"},
            "output": None,
        }
        self.local_server._az_run = lambda *args, **kwargs: self.fail("must not query the Azure CLI default subscription")

        self.assertFalse(self.local_server._reconcile_teardown(record))
        self.assertEqual(record["runtimeStatus"], "Running")

    def test_reconciled_teardown_holds_its_estate_only_while_azure_still_deletes(self) -> None:
        from fastapi import HTTPException

        group = {"status": 200, "body": {"properties": {"provisioningState": "Deleting"}}}

        class Azure:
            def __init__(self, tokens):
                pass

            def call(self, method, url, resource, body=None):
                return group["status"], group["body"]

        started = self._record_started_tasks()
        for end_status, end_body in ((404, None), (200, {"properties": {"provisioningState": "Succeeded"}})):
            with self.subTest(azure_after_deleting=end_status):
                group.update(status=200, body={"properties": {"provisioningState": "Deleting"}})
                started.clear()
                # A restart leaves the interrupted teardown Terminated with no worker.
                record = self._active_record("teardownFull-interrupted", group="rg-a", status="Terminated",
                                             runType="teardown", subscriptionId=self._SUBSCRIPTION)
                record["output"] = {"status": "running", "resources": {}, "phases": [
                    {"phase": "Preflight", "status": "succeeded"},
                    {"phase": "Front-End Resource Groups", "status": "running"},
                ]}
                with patch("shared.full_teardown.Rest", Azure):
                    self.assertEqual(asyncio.run(self.local_server.reconcile_teardowns_endpoint()), {"reconciled": 1})
                    self.assertEqual(record["runtimeStatus"], "Running")
                    # Azure is still deleting the group: no new run and no claimed cancel.
                    self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(group="rg-a"))))
                    with self.assertRaises(HTTPException) as cancelled:
                        asyncio.run(self.local_server.cancel("teardownFull-interrupted"))
                    self.assertEqual(cancelled.exception.status_code, 409)
                    self.assertEqual(record["runtimeStatus"], "Running")

                    group.update(status=end_status, body=end_body)
                    asyncio.run(self.local_server.reconcile_teardowns_endpoint())

                self.assertEqual(record["runtimeStatus"], "Failed")
                self.assertNotEqual(record["customStatus"]["status"], "succeeded")
                self.assertIn("run the teardown again", record["customStatus"]["detail"])
                rerun = asyncio.run(self.local_server.start_teardown(self._teardown(group="rg-a")))
                self.assertEqual(started, [f"teardown:{rerun['instanceId']}"])
                self.local_server.deployments.clear()

    def test_reconciled_workspace_only_teardown_without_a_worker_frees_its_estate(self) -> None:
        class Fabric:
            def __init__(self, tokens):
                pass

            def pages(self, url, resource, key="value"):
                return iter([])

        started = self._record_started_tasks()
        # A restart left a workspace-only teardown Running; no Azure deletion can still be in flight.
        record = self._active_record("teardownPartial-interrupted", workspace="ws-a", runType="teardown",
                                     subscriptionId=self._SUBSCRIPTION)
        with patch("shared.full_teardown.Rest", Fabric):
            self.assertEqual(asyncio.run(self.local_server.reconcile_teardowns_endpoint()), {"reconciled": 1})

        self.assertEqual(record["runtimeStatus"], "Failed")
        self.assertIn("run the teardown again", record["customStatus"]["detail"])
        rerun = asyncio.run(self.local_server.start_teardown(self._teardown(workspace="WS-A")))
        self.assertEqual(started, [f"teardown:{rerun['instanceId']}"])

    def test_teardown_with_failures_is_reported_failed_with_its_phases(self) -> None:
        class FailingTeardown:
            def __init__(self, spec, tokens, report):
                self.report = report

            def run(self):
                self.report.phase("Preflight", "running")
                self.report.phase("Preflight", "succeeded")
                self.report.phase("Azure Resource Group", "running")
                self.report.phase("Azure Resource Group", "failed")
                return {"status": "failed", "failures": ["Azure Resource Group: still deleting"], "deleted": {}, "skipped": []}

        instance_id = "teardownFull-test"
        self.local_server.deployments[instance_id] = {"instanceId": instance_id, "runtimeStatus": "Running",
                                                      "customStatus": {"runType": "teardown", "logs": []}, "output": None}
        request = self.local_server.TeardownRequest(resource_group_name="rg-a", delete_azure_rg=True, subscription_id="sub-a")

        with patch("shared.full_teardown.DeploymentTeardown", FailingTeardown):
            asyncio.run(self.local_server._run_teardown(instance_id, request))

        record = self.local_server.deployments.pop(instance_id)
        self.assertEqual(record["runtimeStatus"], "Failed")
        self.assertEqual(record["customStatus"]["cloudStatus"], "needs_attention")
        self.assertEqual([(p["phase"], p["status"]) for p in record["output"]["phases"]],
                         [("Preflight", "succeeded"), ("Azure Resource Group", "failed")])
        self.assertEqual(record["output"]["teardown"]["failures"], ["Azure Resource Group: still deleting"])

    def _repo_with_ledger(self, workspace: str) -> Path:
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo, True)
        (repo / "orchestrator").mkdir()
        (repo / "state-tracking").mkdir()
        (repo / "state-tracking" / f".deployment-state-{workspace}.json").write_text(json.dumps({"phases": [
            {"resources": {"FabricWorkspaceName": workspace}, "steps": [{"name": "Phase 1: Fabric Workspace", "success": True}]},
        ]}))
        return repo

    def test_deploy_ledger_is_not_backfilled_into_teardown_records(self) -> None:
        repo = self._repo_with_ledger("ws-a")

        def record(run_type: str) -> dict:
            return {"customStatus": {"runType": run_type, "workspaceName": "ws-a"},
                    "output": {"phases": [{"phase": "Preflight", "status": "running"}]}}

        teardown, deploy = record("teardown"), record("deploy")
        with patch.object(self.local_server, "__file__", str(repo / "orchestrator" / "local_server.py")):
            self.local_server._backfill_successful_steps_from_state_tracking("t", teardown)
            self.local_server._backfill_successful_steps_from_state_tracking("d", deploy)

        self.assertEqual([p["phase"] for p in teardown["output"]["phases"]], ["Preflight"])
        self.assertIn("Phase 1: Fabric Workspace", [p["phase"] for p in deploy["output"]["phases"]])

    def test_successful_teardown_removes_only_its_workspace_ledger(self) -> None:
        repo = self._repo_with_ledger("ws-a")
        other = repo / "state-tracking" / ".deployment-state-ws-b.json"
        other.write_text("{}")

        with patch.object(self.local_server, "__file__", str(repo / "orchestrator" / "local_server.py")):
            self.local_server._remove_deployment_state("../state-tracking/x", lambda *args: None)
            self.local_server._remove_deployment_state("ws-a", lambda *args: None)

        self.assertFalse((repo / "state-tracking" / ".deployment-state-ws-a.json").exists())
        self.assertTrue(other.exists())

    def test_deploy_request_rejects_cardiology_prefix_longer_than_twelve_chars(self) -> None:
        base = {
            "fabric_workspace_name": "med-1028",
            "resource_group_name": "rg-med-1028",
            "expected_tenant_id": "00000000-0000-0000-0000-000000000001",
            "expected_subscription_id": "00000000-0000-0000-0000-000000000002",
        }
        valid = self.local_server.DeployRequest(**base, cardiology_prefix="cardioed1028")
        self.assertEqual(valid.cardiology_prefix, "cardioed1028")
        with self.assertRaisesRegex(Exception, "3–12 lowercase letters/digits"):
            self.local_server.DeployRequest(**base, cardiology_prefix="cardiomed1027")

    def test_chained_continuation_inherits_successful_phases_from_ancestor_runs(self) -> None:
        run_a = {
            "instanceId": "run-a",
            "runtimeStatus": "Failed",
            "customStatus": {"workspaceName": "med-1102", "resourceGroupName": "rg-med-1102", "logs": []},
            "output": {
                "phases": [
                    {"phase": "Phase 2: Fabric RTI", "status": "succeeded"},
                    {"phase": "Phase 3: HDS Source Deployment", "status": "succeeded"},
                    {"phase": "Phase 2: Fabric RTI Enrichment (auto)", "status": "succeeded"},
                ]
            },
        }
        run_b = {
            "instanceId": "run-b",
            "runtimeStatus": "Failed",
            "customStatus": {
                "workspaceName": "med-1102",
                "resourceGroupName": "rg-med-1102",
                "continuedFrom": "run-a",
                "logs": [],
            },
            "output": {
                "phases": [
                    {"phase": "Phase 3: DICOM Shortcut + HDS Pipelines (auto)", "status": "succeeded"},
                ]
            },
        }
        self.local_server.deployments["run-a"] = run_a
        self.local_server.deployments["run-b"] = run_b
        self.addCleanup(self.local_server.deployments.pop, "run-a", None)
        self.addCleanup(self.local_server.deployments.pop, "run-b", None)

        req = self.local_server.DeployRequest(
            fabric_workspace_name="med-1102",
            resource_group_name="rg-med-1102",
            expected_tenant_id="11111111-2222-4333-8444-555555555555",
            expected_subscription_id="22222222-3333-4444-8555-666666666666",
            continue_from_instance_id="run-b",
        )
        with (
            patch.object(
                self.local_server,
                "_cloud_state_sync",
                return_value={"workspace": {"exists": True}, "resourceGroup": {"exists": True}},
            ),
            patch.object(
                self.local_server,
                "_live_resume_prerequisites",
                return_value={},
            ),
            patch.object(
                self.local_server,
                "_phase_live_prerequisites_ok",
                return_value=(True, "ok"),
            ),
        ):
            applied = self.local_server._apply_success_skips_from_deployment(req, run_b, "Continue-from-failure")

        self.assertTrue(applied)
        self.assertTrue(req.reuse_fabric_rti)
        self.assertTrue(req.skip_rti_phase2)
        self.assertTrue(req.skip_hds_source)
        self.assertTrue(req.skip_hds_pipelines)

    def test_tagged_warn_and_info_lines_do_not_block_phase_skip(self) -> None:
        # med-1109: a recovered "[WARN] ACL attempt 1 failed ... retry" stored at level=error made
        # continue-from-failure re-run the 107-minute HDS pipelines phase.
        phase = "PHASE 3: DICOM SHORTCUT + HDS PIPELINES (AUTO)"
        recovered = [
            "WARNING: [2026-11-09 20:10:47Z][WARN]    ACL attempt 1 failed (RBAC not yet propagated). Waiting 60s before retry...",
            "[2026-11-10 01:10:34Z][INFO]    CMA pipeline status: Failed (0.5 min elapsed)",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "logs"
            logs.mkdir()
            with patch.object(self.local_server, "DATA_DIR", Path(tmp)):
                def blocking(messages: list[str]) -> bool:
                    (logs / "run.jsonl").write_text(
                        "".join(json.dumps({"phase": phase, "level": "error", "message": m}) + "\n" for m in messages),
                        encoding="utf-8",
                    )
                    return self.local_server._phase_has_blocking_logs({"instanceId": "run"}, phase)

                self.assertFalse(blocking(recovered))
                self.assertTrue(blocking(recovered + ["[2026-11-10 01:10:35Z][ERROR]    Clinical pipeline Failed"]))
                self.assertTrue(blocking(recovered + ["ERROR: (AuthorizationFailed) az role assignment create failed"]))

    @unittest.skipIf(sys.platform == "win32", "POSIX-only process group test")
    def test_posix_cancel_terminates_process_group_including_grandchild(self) -> None:
        import subprocess
        import time

        instance_id = "test-cancel-posix-group"
        self.local_server.deployments[instance_id] = {
            "runtimeStatus": "Running",
            "customStatus": {"status": "running"},
            "createdTime": "2026-11-13T00:00:00+00:00",
        }
        proc = subprocess.Popen(
            ["sh", "-c", "sleep 60 & wait"],
            start_new_session=True,
        )
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        pgid = proc.pid
        self.local_server.active_processes[instance_id] = proc.pid
        time.sleep(0.2)

        ps_before = subprocess.run(
            ["ps", "-o", "pid,command", "-g", str(pgid)],
            capture_output=True,
            text=True,
        )
        self.assertIn("sleep", ps_before.stdout)

        asyncio.run(self.local_server.cancel(instance_id))

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            ps_check = subprocess.run(
                ["ps", "-o", "pid,stat,command", "-g", str(pgid)],
                capture_output=True,
                text=True,
            )
            active_lines = [
                line for line in ps_check.stdout.strip().splitlines()[1:]
                if len(line.split()) > 1 and "Z" not in line.split()[1]
            ]
            if not active_lines:
                break
            time.sleep(0.05)

        proc.poll()
        ps_after = subprocess.run(
            ["ps", "-o", "pid,command", "-g", str(pgid)],
            capture_output=True,
            text=True,
        )
        self.assertNotIn("sleep", ps_after.stdout)
        self.assertNotIn(str(proc.pid), ps_after.stdout)
        self.assertEqual(
            self.local_server.deployments[instance_id]["runtimeStatus"],
            "Terminated",
        )
    def test_failed_deploy_cleans_up_active_processes_in_finally(self) -> None:
        """When run_deploy raises an exception, instance_id is popped from active_processes in finally (R-1)."""
        import activities.invoke_powershell as ip

        instance_id = "test-fail-cleanup"
        self.local_server.deployments[instance_id] = {
            "instanceId": instance_id,
            "runtimeStatus": "Running",
            "customStatus": {"status": "running"},
            "createdTime": "2026-11-13T00:00:00+00:00",
            "output": None,
        }
        req = self.local_server.DeployRequest(
            fabric_workspace_name="ws",
            resource_group_name="rg",
            expected_tenant_id="00000000-0000-0000-0000-000000000001",
            expected_subscription_id="00000000-0000-0000-0000-000000000002",
        )

        def failing_run_deploy(config, step_callback=None, pid_callback=None):
            if pid_callback:
                pid_callback(999888)
            self.assertEqual(self.local_server.active_processes.get(instance_id), 999888)
            raise RuntimeError("Simulated deploy failure")

        with patch.object(ip, "run_deploy", failing_run_deploy):
            asyncio.run(self.local_server._run_deploy(instance_id, req))

        self.assertEqual(self.local_server.deployments[instance_id]["runtimeStatus"], "Failed")
        self.assertNotIn(instance_id, self.local_server.active_processes)

    @unittest.skipIf(sys.platform == "win32", "POSIX-only process group test")
    def test_kill_process_group_safety_guards(self) -> None:
        """_kill_process_group refuses when pgid == server pgid or pgid != pid (R-1)."""
        import subprocess

        # Child started in current process group (pgid == os.getpgrp())
        child = subprocess.Popen(["sleep", "10"])
        self.addCleanup(lambda: child.poll() is None and child.kill())
        self.assertEqual(os.getpgid(child.pid), os.getpgrp())

        with self.assertLogs("local_server", level="WARNING") as cm:
            survived = self.local_server._kill_process_group(child.pid)

        self.assertFalse(survived)
        self.assertTrue(any("Refusing to kill process group" in log for log in cm.output))
        # Child should still be alive
        self.assertIsNone(child.poll())

    # ── Concurrent-run guard: one active run per estate (workspace or resource group) ──

    _TENANT = "00000000-0000-0000-0000-000000000001"
    _SUBSCRIPTION = "00000000-0000-0000-0000-000000000002"

    def _active_record(self, instance_id: str, workspace: str = "", group: str = "", status: str = "Running", **custom) -> dict:
        record = {"instanceId": instance_id, "runtimeStatus": status, "createdTime": "2026-11-14T00:00:00+00:00",
                  "customStatus": {"workspaceName": workspace, "resourceGroupName": group, "logs": [], **custom},
                  "output": None}
        self.local_server.deployments[instance_id] = record
        return record

    def _record_started_tasks(self) -> list[str]:
        started: list[str] = []

        def record_task(coro, name):
            started.append(name)
            coro.close()

        self.local_server._create_logged_task = record_task
        self.addCleanup(self.local_server.deployments.clear)
        return started

    def _teardown(self, workspace: str = "", group: str = ""):
        return self.local_server.TeardownRequest(fabric_workspace_name=workspace, resource_group_name=group,
                                                 subscription_id=self._SUBSCRIPTION)

    def _deploy_request(self, workspace: str, group: str):
        return self.local_server.DeployRequest(fabric_workspace_name=workspace, resource_group_name=group,
                                               expected_tenant_id=self._TENANT, expected_subscription_id=self._SUBSCRIPTION)

    @contextlib.contextmanager
    def _deploy_gates(self, preflight=None):
        async def no_deploy_run(*args, **kwargs):
            return None

        with (
            patch("activities.addons.preflight", side_effect=preflight or (lambda config: [])),
            patch.object(self.local_server, "_apply_prior_success_skips"),
            patch.object(self.local_server, "_get_auth_context_sync", return_value={"ready": True}),
            patch.object(self.local_server, "_run_deploy", no_deploy_run),
        ):
            yield

    def _start_deploy(self, request, preflight=None):
        with self._deploy_gates(preflight):
            return asyncio.run(self.local_server.start_deploy(request))

    @staticmethod
    def _slow_preflight(config):
        raise AssertionError("a conflicting deploy must be refused before its slow preflight runs")

    def _assert_refused(self, call) -> None:
        from fastapi import HTTPException

        before = dict(self.local_server.deployments)
        with self.assertRaises(HTTPException) as raised:
            call()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, "Another deployment or teardown is active for this estate")
        self.assertEqual(self.local_server.deployments, before)

    def test_deploy_is_refused_while_another_run_targets_the_same_workspace(self) -> None:
        started = self._record_started_tasks()
        self._active_record("P1-running", workspace="ws-a", group="rg-a")

        self._assert_refused(lambda: self._start_deploy(self._deploy_request("ws-a", "rg-other"), preflight=self._slow_preflight))
        self.assertEqual(started, [])

    def test_deploy_rechecks_the_estate_after_its_last_await(self) -> None:
        started = self._record_started_tasks()

        def concurrent_start(config):
            # Another request reserves the estate while this one awaits its preflight.
            self._active_record("teardownFull-concurrent", workspace="ws-a", group="rg-a", runType="teardown")
            return []

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as raised:
            self._start_deploy(self._deploy_request("ws-a", "rg-a"), preflight=concurrent_start)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(list(self.local_server.deployments), ["teardownFull-concurrent"])
        self.assertEqual(started, [])

    def test_teardown_is_refused_while_a_deploy_runs_on_the_same_resource_group(self) -> None:
        started = self._record_started_tasks()
        self._active_record("P1-running", workspace="ws-a", group="rg-a", status="Pending")

        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(group="rg-a"))))
        self.assertEqual(started, [])

    def test_runs_for_different_estates_start_concurrently(self) -> None:
        started = self._record_started_tasks()
        self._active_record("P1-running", workspace="ws-a", group="rg-a")

        deploy = self._start_deploy(self._deploy_request("ws-b", "rg-b"))
        teardown = asyncio.run(self.local_server.start_teardown(self._teardown("ws-c", "rg-c")))

        self.assertEqual(self.local_server.deployments[deploy["instanceId"]]["runtimeStatus"], "Running")
        self.assertEqual(self.local_server.deployments[teardown["instanceId"]]["runtimeStatus"], "Running")
        self.assertEqual(len(started), 2)
        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(group="rg-b"))))

    def test_estate_names_compare_case_insensitively(self) -> None:
        self._record_started_tasks()
        self._active_record("P1-running", workspace="Med-Estate", group="RG-Med-Estate")

        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(workspace="med-estate"))))
        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(group="rg-med-estate"))))

    def test_empty_estate_names_never_match(self) -> None:
        started = self._record_started_tasks()
        self._active_record("teardownPartial-ws-only", workspace="ws-a", group="", runType="teardown")

        asyncio.run(self.local_server.start_teardown(self._teardown(workspace="ws-b", group="")))
        self.assertEqual(len(started), 1)
        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(workspace="WS-A"))))

    def test_imported_peer_history_never_blocks(self) -> None:
        started = self._record_started_tasks()
        self._active_record("P1-peer", workspace="ws-a", group="rg-a", importedFrom="peer-sandbox")

        asyncio.run(self.local_server.start_teardown(self._teardown("ws-a", "rg-a")))
        self.assertEqual(len(started), 1)
        self._assert_refused(lambda: self._start_deploy(self._deploy_request("ws-a", "rg-a")))

    def test_teardown_batch_parent_never_blocks(self) -> None:
        started = self._record_started_tasks()
        self._active_record("teardownBatch-parent", workspace="ws-a", group="rg-a", runType="teardownBatch")

        deploy = self._start_deploy(self._deploy_request("ws-a", "rg-a"))
        self.assertEqual(len(started), 1)
        self.assertIn(deploy["instanceId"], self.local_server.deployments)
        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown(self._teardown(group="rg-a"))))

    def test_teardown_batch_with_a_colliding_job_starts_nothing(self) -> None:
        started = self._record_started_tasks()
        self._active_record("P1-running", workspace="ws-a", group="rg-a")
        batch = self.local_server.TeardownBatchRequest(jobs=[self._teardown("ws-x", "rg-x"), self._teardown(group="RG-A")])

        self._assert_refused(lambda: asyncio.run(self.local_server.start_teardown_batch(batch)))
        self.assertEqual(started, [])

    def test_teardown_batch_with_duplicate_jobs_starts_nothing(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        for jobs in ([self._teardown("ws-x", "rg-x"), self._teardown(group="RG-X")],
                     [self._teardown("ws-x", ""), self._teardown("WS-X", "rg-y")]):
            with self.subTest(jobs=[(j.fabric_workspace_name, j.resource_group_name) for j in jobs]):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(self.local_server.start_teardown_batch(self.local_server.TeardownBatchRequest(jobs=jobs)))
                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(started, [])
                self.assertEqual(self.local_server.deployments, {})
        # Jobs with only empty names in common are distinct estates.
        result = asyncio.run(self.local_server.start_teardown_batch(self.local_server.TeardownBatchRequest(
            jobs=[self._teardown("ws-x", ""), self._teardown("", "rg-y")])))
        self.assertEqual(len(result["instanceIds"]), 2)

    def _addon_deployment(self, instance_id: str, workspace: str, group: str, status: str = "Completed", **custom) -> dict:
        record = self._active_record(instance_id, workspace=workspace, group=group, status=status, **custom)
        record["customStatus"]["deployConfig"] = self._deploy_request(workspace, group).model_dump()
        return record

    def _start_addons(self, instance_id: str, names: list[str]):
        async def no_addon_run(*args, **kwargs):
            return None

        with (
            patch("activities.addons.preflight", return_value=[]),
            patch.object(self.local_server, "_run_later_addons", no_addon_run),
        ):
            return asyncio.run(self.local_server.start_addons(instance_id, {"addons": names}))

    def test_addon_run_is_refused_while_another_run_targets_the_estate(self) -> None:
        self._record_started_tasks()
        deployment = self._addon_deployment("P1-done", "ws-a", "rg-a")
        self._active_record("teardownFull-running", workspace="", group="RG-A", runType="teardown")

        self._assert_refused(lambda: self._start_addons("P1-done", ["rayfin"]))
        self.assertEqual(deployment["runtimeStatus"], "Completed")

    def test_addon_guard_excludes_the_deployment_itself(self) -> None:
        self._record_started_tasks()
        # A paused Databricks add-on keeps this deployment Running; it must not block its own sibling add-on.
        deployment = self._addon_deployment("P1-paused", "ws-a", "rg-a", status="Running",
                                            addons={"databricks": {"status": "paused"}})
        self.local_server._addon_tasks["P1-paused"] = set()
        self.addCleanup(self.local_server._addon_tasks.pop, "P1-paused", None)

        result = self._start_addons("P1-paused", ["rayfin"])

        self.assertEqual(result["addons"], ["rayfin"])
        self.assertEqual(deployment["customStatus"]["addons"]["rayfin"]["status"], "pending")
        self.local_server._addon_tasks["P1-paused"] = set()
        deployment["customStatus"]["addons"]["rayfin"]["status"] = "failed"
        self._active_record("P1-other", workspace="ws-a", group="rg-other")
        self._assert_refused(lambda: self._start_addons("P1-paused", ["rayfin"]))

    def _assert_estate_conflict(self, raised) -> None:
        self.assertEqual(raised.status_code, 409)
        self.assertEqual(raised.detail, "Another deployment or teardown is active for this estate")

    def test_live_addon_worker_under_a_completed_deployment_holds_its_estate(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        # _run_deploy marks the base Completed, then runs the requested add-ons as a tracked worker.
        deployment = self._addon_deployment("P1-chained", "ws-a", "rg-a", addons={"databricks": {"status": "running"}})
        release: asyncio.Event | None = None

        class AwaitingAddons:
            def __init__(self, *args):
                pass

            async def run(self, names, fresh_export=False):
                await release.wait()

        async def refused(start) -> None:
            before = dict(self.local_server.deployments)
            with self.assertRaises(HTTPException) as raised:
                await start
            self._assert_estate_conflict(raised.exception)
            self.assertEqual(self.local_server.deployments, before)

        async def scenario():
            nonlocal release
            release = asyncio.Event()
            worker = asyncio.create_task(self.local_server._run_later_addons(
                "P1-chained", deployment["customStatus"]["deployConfig"], ["databricks"], fresh_export=False))
            self.local_server._track_addon_task("P1-chained", worker)
            await asyncio.sleep(0)
            self.assertEqual(deployment["runtimeStatus"], "Completed")

            await refused(self.local_server.start_teardown(self._teardown(group="RG-A")))
            await refused(self.local_server.start_teardown_batch(self.local_server.TeardownBatchRequest(
                jobs=[self._teardown("ws-x", "rg-x"), self._teardown(workspace="WS-A")])))
            await refused(self.local_server.start_deploy(self._deploy_request("ws-a", "rg-other")))
            self.assertEqual(started, [])
            unrelated = await self.local_server.start_teardown(self._teardown("ws-b", "rg-b"))

            release.set()
            await worker
            self.assertEqual(deployment["runtimeStatus"], "Completed")
            freed = await self.local_server.start_teardown(self._teardown("ws-a", "rg-a"))
            self.assertEqual(started, [f"teardown:{unrelated['instanceId']}", f"teardown:{freed['instanceId']}"])

        with self._deploy_gates(self._slow_preflight), patch("activities.addons.AddonRunner", AwaitingAddons):
            asyncio.run(scenario())

    def test_teardown_worker_holds_its_estate_until_its_deletion_ends(self) -> None:
        from fastapi import HTTPException

        deleting, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(self.local_server.deployments.clear)

        class SlowDeletion:
            def __init__(self, spec, tokens, report):
                self.report = report

            def run(self):
                self.report.phase("Azure Resource Group", "running")
                deleting.set()
                release.wait(10)
                self.report.phase("Azure Resource Group", "failed")
                return {"status": "failed", "failures": ["Azure Resource Group: still deleting"], "deleted": {}, "skipped": []}

        class NoAzure:
            def __init__(self, tokens):
                raise AssertionError("a teardown with a live worker must not be reconciled")

        def preflight(config):
            return [] if release.is_set() else self._slow_preflight(config)

        async def scenario():
            teardown_id = (await self.local_server.start_teardown(self._teardown("ws-a", "rg-a")))["instanceId"]
            record = self.local_server.deployments[teardown_id]
            self.assertTrue(await asyncio.to_thread(deleting.wait, 10))

            # Deletion cannot be interrupted, so cancel must not claim success or free the estate.
            with self.assertRaises(HTTPException) as cancelled:
                await self.local_server.cancel(teardown_id)
            self.assertEqual(cancelled.exception.status_code, 409)
            self.assertEqual(await self.local_server.reconcile_teardowns_endpoint(), {"reconciled": 0})
            self.assertEqual(record["runtimeStatus"], "Running")
            with self.assertRaises(HTTPException) as refused:
                await self.local_server.start_deploy(self._deploy_request("WS-A", "rg-other"))
            self._assert_estate_conflict(refused.exception)
            self.assertEqual(list(self.local_server.deployments), [teardown_id])

            release.set()

            async def settled():
                while record["runtimeStatus"] == "Running":
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(settled(), 10)
            self.assertEqual(record["runtimeStatus"], "Failed")
            deploy = await self.local_server.start_deploy(self._deploy_request("ws-a", "rg-a"))
            self.assertEqual(self.local_server.deployments[deploy["instanceId"]]["runtimeStatus"], "Running")

        with (
            self._deploy_gates(preflight),
            patch("shared.full_teardown.DeploymentTeardown", SlowDeletion),
            patch("shared.full_teardown.Rest", NoAzure),
        ):
            asyncio.run(scenario())

    # ── History mutation must never hide a live run from the estate guard ──

    def _history_store(self, *records: dict) -> dict:
        """Back the history routes with an in-memory deployments table holding copies of ``records``."""
        store = {record["instanceId"]: dict(record) for record in records}

        def clear() -> int:
            count = len(store)
            store.clear()
            return count

        for name, fake in (("db_list_deployments", lambda: list(store.values())),
                           ("db_delete_deployment", lambda instance_id: store.pop(instance_id, None) is not None),
                           ("db_clear_all", clear), ("get_deployment", store.get)):
            patcher = patch.object(self.local_server, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        return store

    def test_history_delete_refuses_a_record_whose_worker_still_runs_whatever_its_status(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        server = self.local_server
        addon = self._active_record("P1-addon", workspace="ws-a", group="rg-a", status="Completed")
        teardown = self._active_record("teardownFull-b", workspace="ws-b", group="rg-b", status="Failed", runType="teardown")
        cancelled = self._active_record("teardownFull-c", workspace="ws-c", group="rg-c", status="Terminated", runType="teardown")
        running = self._active_record("P1-running", workspace="ws-d", group="rg-d")
        store = self._history_store(addon, teardown, cancelled, running)

        async def refused_delete(instance_id: str) -> None:
            with self.assertRaises(HTTPException) as raised:
                await server.delete_deployment_endpoint(instance_id)
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn(instance_id, server.deployments)
            self.assertIn(instance_id, store)

        async def refused_start(workspace: str, group: str) -> None:
            with self.assertRaises(HTTPException) as raised:
                await server.start_teardown(self._teardown(workspace, group))
            self._assert_estate_conflict(raised.exception)

        async def scenario():
            gate = asyncio.Event()
            addon_worker, teardown_worker, cancelled_worker = (asyncio.create_task(gate.wait()) for _ in range(3))
            server._track_addon_task("P1-addon", addon_worker)
            server._teardown_tasks["teardownFull-b"] = teardown_worker
            server._teardown_tasks["teardownFull-c"] = cancelled_worker
            await asyncio.sleep(0)

            for instance_id, workspace, group in (("P1-addon", "WS-A", ""), ("teardownFull-b", "", "RG-B"),
                                                  ("teardownFull-c", "ws-c", ""), ("P1-running", "", "rg-d")):
                with self.subTest(instance_id=instance_id):
                    await refused_delete(instance_id)
                    await refused_start(workspace, group)
            self.assertEqual(started, [])

            gate.set()
            await asyncio.gather(addon_worker, teardown_worker, cancelled_worker)
            for instance_id in ("P1-addon", "teardownFull-b", "teardownFull-c"):
                with self.subTest(released=instance_id):
                    self.assertEqual(await server.delete_deployment_endpoint(instance_id), {"message": "Deleted"})
                    self.assertNotIn(instance_id, server.deployments)
                    self.assertNotIn(instance_id, store)
            await refused_delete("P1-running")
            freed = await server.start_teardown(self._teardown("ws-a", "rg-b"))
            self.assertEqual(started, [f"teardown:{freed['instanceId']}"])

        asyncio.run(scenario())

    def test_history_clear_retains_active_records_and_removes_inactive_ones(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        server = self.local_server
        records = [
            self._active_record("P1-addon", workspace="ws-a", group="rg-a", status="Completed"),
            self._active_record("teardownFull-b", workspace="ws-b", group="rg-b", status="Terminated", runType="teardown"),
            self._active_record("P1-running", workspace="ws-c", group="rg-c", status="Pending"),
            self._active_record("P1-peer", workspace="ws-d", group="rg-d", importedFrom="peer-sandbox"),
            self._active_record("P1-done", workspace="ws-e", group="rg-e", status="Completed"),
            self._active_record("P1-failed", workspace="ws-f", group="rg-f", status="Failed"),
            self._active_record("teardownFull-old", workspace="ws-g", group="rg-g", status="Failed", runType="teardown"),
        ]
        store = self._history_store(*records, {"instanceId": "P1-db-only", "runtimeStatus": "Completed",
                                               "customStatus": {"workspaceName": "ws-h"}})
        active = {"P1-addon", "teardownFull-b", "P1-running"}

        async def refused_start(workspace: str, group: str) -> None:
            with self.assertRaises(HTTPException) as raised:
                await server.start_teardown(self._teardown(workspace, group))
            self._assert_estate_conflict(raised.exception)

        async def scenario():
            gate = asyncio.Event()
            addon_worker, teardown_worker = asyncio.create_task(gate.wait()), asyncio.create_task(gate.wait())
            finished_addon, finished_teardown = asyncio.create_task(asyncio.sleep(0)), asyncio.create_task(asyncio.sleep(0))
            await asyncio.gather(finished_addon, finished_teardown)
            server._track_addon_task("P1-addon", addon_worker)
            server._teardown_tasks["teardownFull-b"] = teardown_worker
            server._track_addon_task("P1-done", finished_addon)
            server._teardown_tasks["teardownFull-old"] = finished_teardown

            self.assertEqual(await server.clear_all_deployments_endpoint(), {"message": "Cleared 5 deployments"})
            self.assertEqual(set(server.deployments), active)
            self.assertEqual(set(store), active)
            await refused_start("ws-a", "")
            await refused_start("", "RG-B")
            await refused_start("WS-C", "")
            self.assertEqual(started, [])

            gate.set()
            await asyncio.gather(addon_worker, teardown_worker)
            self.assertEqual(await server.clear_all_deployments_endpoint(), {"message": "Cleared 2 deployments"})
            self.assertEqual(set(server.deployments), {"P1-running"})
            self.assertEqual(set(store), {"P1-running"})
            await refused_start("ws-c", "")
            freed = await server.start_teardown(self._teardown("ws-a", "rg-b"))
            self.assertEqual(started, [f"teardown:{freed['instanceId']}"])

        asyncio.run(scenario())

    def test_history_clear_without_active_work_clears_everything(self) -> None:
        self._record_started_tasks()
        self._active_record("P1-done", workspace="ws-a", group="rg-a", status="Completed")
        self._active_record("teardownFull-old", workspace="ws-b", group="rg-b", status="Failed", runType="teardown")
        store = self._history_store(*self.local_server.deployments.values(),
                                    {"instanceId": "P1-db-only", "runtimeStatus": "Terminated", "customStatus": {}})

        self.assertEqual(asyncio.run(self.local_server.clear_all_deployments_endpoint()), {"message": "Cleared 3 deployments"})
        self.assertEqual(self.local_server.deployments, {})
        self.assertEqual(store, {})

    def _imported_peer_record(self, instance_id: str, workspace: str, status: str = "Completed") -> dict:
        return {"instanceId": instance_id, "runtimeStatus": status,
                "customStatus": {"workspaceName": workspace, "resourceGroupName": "", "importedFrom": "peer-sandbox"}}

    def test_local_addons_on_imported_history_hold_its_estate_from_preflight_until_the_worker_ends(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        server = self.local_server
        base = self._addon_deployment("P1-imported", "ws-a", "rg-a", importedFrom="peer-sandbox")
        store = self._history_store(base, self._imported_peer_record("P1-peer-old", "ws-p"))
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        gate: asyncio.Event | None = None

        def slow_preflight(config):
            entered.set()
            release.wait(10)
            return []

        class AwaitingAddons:
            def __init__(self, *args):
                pass

            async def run(self, names, fresh_export=False):
                await gate.wait()

        async def estate_held() -> None:
            for workspace, group in (("WS-A", ""), ("", "rg-a")):
                with self.assertRaises(HTTPException) as raised:
                    await server.start_teardown(self._teardown(workspace, group))
                self._assert_estate_conflict(raised.exception)
            with self.assertRaises(HTTPException) as raised:
                await server.delete_deployment_endpoint("P1-imported")
            self.assertEqual(raised.exception.status_code, 409)
            await server.clear_all_deployments_endpoint()
            self.assertIs(server.deployments.get("P1-imported"), base)
            self.assertIn("P1-imported", store)

        async def scenario():
            nonlocal gate
            gate = asyncio.Event()
            start = asyncio.create_task(server.start_addons("P1-imported", {"addons": ["rayfin"]}))
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            self.assertEqual(base["runtimeStatus"], "Pending")
            await estate_held()
            self.assertNotIn("P1-peer-old", store)  # Imported history with no local work stays removable.

            release.set()
            self.assertEqual(await start, {"instanceId": "P1-imported", "addons": ["rayfin"]})
            (worker,) = server._addon_tasks["P1-imported"]
            await estate_held()
            # A later peer import must not swap the locally owned run back to read-only history.
            server._merge_imported_deployments([self._imported_peer_record("P1-imported", "ws-a")])
            self.assertIs(server.deployments["P1-imported"], base)
            await estate_held()
            self.assertEqual(started, [])

            gate.set()
            await worker
            self.assertEqual(base["runtimeStatus"], "Completed")
            self.assertEqual(await server.delete_deployment_endpoint("P1-imported"), {"message": "Deleted"})
            freed = await server.start_teardown(self._teardown("ws-a", "rg-a"))
            self.assertEqual(started, [f"teardown:{freed['instanceId']}"])

        with (
            patch("activities.addons.preflight", side_effect=slow_preflight),
            patch("activities.addons.AddonRunner", AwaitingAddons),
        ):
            asyncio.run(scenario())

    def test_failed_addon_preflight_leaves_imported_history_removable_and_non_blocking(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        server = self.local_server
        base = self._addon_deployment("P1-imported", "ws-a", "rg-a", importedFrom="peer-sandbox")
        store = self._history_store(base)

        with patch("activities.addons.preflight", return_value=[{"status": "fail", "message": "capacity paused"}]):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(server.start_addons("P1-imported", {"addons": ["rayfin"]}))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(base["runtimeStatus"], "Completed")
        self.assertEqual(base["customStatus"]["importedFrom"], "peer-sandbox")

        asyncio.run(server.start_teardown(self._teardown("ws-a", "rg-a")))
        self.assertEqual(len(started), 1)
        self.assertEqual(asyncio.run(server.delete_deployment_endpoint("P1-imported")), {"message": "Deleted"})
        self.assertNotIn("P1-imported", store)

    def test_live_local_worker_outranks_imported_provenance(self) -> None:
        from fastapi import HTTPException

        started = self._record_started_tasks()
        server = self.local_server
        # A worker started under a record that still carries peer provenance (created before adoption).
        record = self._active_record("P1-pre-adoption", workspace="ws-a", group="rg-a", status="Completed",
                                     importedFrom="peer-sandbox")
        store = self._history_store(record)

        async def scenario():
            gate = asyncio.Event()
            worker = asyncio.create_task(gate.wait())
            server._track_addon_task("P1-pre-adoption", worker)
            await asyncio.sleep(0)

            with self.assertRaises(HTTPException) as raised:
                await server.start_teardown(self._teardown("", "RG-A"))
            self._assert_estate_conflict(raised.exception)
            with self.assertRaises(HTTPException) as raised:
                await server.delete_deployment_endpoint("P1-pre-adoption")
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(await server.clear_all_deployments_endpoint(), {"message": "Cleared 0 deployments"})
            server._merge_imported_deployments([self._imported_peer_record("P1-pre-adoption", "ws-other")])
            self.assertIs(server.deployments["P1-pre-adoption"], record)
            self.assertEqual(started, [])

            gate.set()
            await worker
            await server.start_teardown(self._teardown("ws-a", "rg-a"))
            self.assertEqual(len(started), 1)
            self.assertEqual(await server.delete_deployment_endpoint("P1-pre-adoption"), {"message": "Deleted"})
            self.assertNotIn("P1-pre-adoption", store)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
