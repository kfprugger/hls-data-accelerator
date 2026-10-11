from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from activities import addons


class AddonContractTests(unittest.TestCase):
    def config(self, **options):
        return {"expected_tenant_id": "11111111-1111-1111-1111-111111111111",
                "expected_subscription_id": "22222222-2222-2222-2222-222222222222",
                "fabric_workspace_name": "med-test", "location": "eastus2", "cardiology_location": "eastus2", **options}

    def test_cli_json_parser_ignores_informational_prefix(self):
        output = '[rayfin] using ambient token from RAYFIN_TOKEN\n{"deployment":{"hostingUrl":"https://app.example"}}\n'
        self.assertEqual(
            addons.parse_cli_json(output, "Rayfin status")["deployment"]["hostingUrl"],
            "https://app.example",
        )

    def test_cli_json_parser_rejects_output_without_an_object(self):
        with self.assertRaisesRegex(RuntimeError, "returned no JSON object"):
            addons.parse_cli_json("[rayfin] no status available\n", "Rayfin status")


    def test_explicit_model_requires_exact_version_and_fifty_free(self):
        config = self.config(deploy_cardiology=True, cardiology_chat_model="chosen", cardiology_chat_model_version="2026-07-09")
        def az(_config, *args):
            if args[1] == "model":
                return [{"model": {"name": "chosen", "version": "2026-07-09", "skus": [{"name": "DataZoneStandard"}]}}]
            return [{"name": {"value": "OpenAI.DataZoneStandard.chosen"}, "limit": 100, "currentValue": 50}]
        with patch.object(addons, "az_json", side_effect=az), patch.object(addons.Cloud, "call", return_value={"defaultUserRolePermissions": {"allowedToCreateApps": True}}):
            self.assertTrue(all(c["status"] == "pass" for c in addons.preflight(config)))
            config["cardiology_chat_model_version"] = "wrong-version"
            checks = addons.preflight(config)
            self.assertEqual(next(c for c in checks if c["name"] == "Cardiology model quota")["status"], "fail")
    def test_databricks_rejects_regions_not_offered_by_provider(self):
        config = self.config(deploy_databricks=True)
        provider = {"registrationState": "Registered", "resourceTypes": [
            {"resourceType": "workspaces", "locations": ["East US 2"]}]}
        locations = {"value": [{"name": "eastus2", "displayName": "East US 2"},
                               {"name": "westus2", "displayName": "West US 2"}]}
        with patch.object(addons, "az_json", return_value=provider), \
             patch.object(addons.Cloud, "call", return_value=locations), \
             patch.object(addons.shutil, "which", return_value="/usr/bin/tool"):
            self.assertEqual(addons.preflight(config)[0]["status"], "pass")
            config["location"] = "westus2"
            result = addons.preflight(config)[0]
            self.assertEqual(result["status"], "fail")
            self.assertIn("not offered in westus2", result["message"])


    def test_fabric_requests_are_attributed_and_tenant_pinned(self):
        cloud = addons.Cloud(self.config())
        cloud.tokens.tenant_id = self.config()["expected_tenant_id"]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return json.dumps({"value": []}).encode()
        with patch.object(cloud.tokens, "token", return_value="not-a-real-token"), patch.object(addons.urllib.request, "urlopen", return_value=Response()) as opening:
            cloud.call("GET", addons.FABRIC + "/v1/workspaces", skill="spark-cli")
            request = opening.call_args.args[0]
            self.assertEqual(request.get_header("X-ms-fabric-skill"), "spark-cli")
            cloud.tokens.tenant_id = "different-tenant"
            with self.assertRaisesRegex(RuntimeError, "tenant differs"):
                cloud.call("GET", addons.FABRIC + "/v1/workspaces")
            self.assertEqual(opening.call_count, 1)
    def test_non_json_api_response_is_an_actionable_failure(self):
        cloud = addons.Cloud(self.config())
        cloud.tokens.tenant_id = self.config()["expected_tenant_id"]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return b"<html>private login redirect content</html>"
        with patch.object(cloud.tokens, "token", return_value="not-a-real-token"), \
             patch.object(addons.urllib.request, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "accounts.azuredatabricks.net returned a non-JSON API response") as error:
                cloud.call("GET", "https://accounts.azuredatabricks.net/api/2.0/accounts", addons.DATABRICKS)
        self.assertNotIn("private login", str(error.exception))

    def test_relative_fabric_continuation_stays_on_the_original_origin(self):
        cloud = object.__new__(addons.Cloud)
        cloud.call = Mock(side_effect=[
            {"value": [{"id": "first"}], "continuationUri": "/v1/workspaces?continuationToken=next"},
            {"value": [{"id": "second"}]},
        ])
        self.assertEqual(
            [item["id"] for item in cloud.items(addons.FABRIC + "/v1/workspaces")],
            ["first", "second"],
        )
        self.assertEqual(
            cloud.call.call_args_list[1].args[1],
            addons.FABRIC + "/v1/workspaces?continuationToken=next",
        )


    def test_selection_does_not_add_unrequested_services(self):
        self.assertEqual(addons.selected({"deploy_rayfin_apps": True}), ["rayfin"])
        self.assertEqual(addons.selected({}), [])
        self.assertEqual(addons.selected({
            "deploy_databricks": True,
            "deploy_rayfin_apps": True,
            "deploy_cardiology": True,
        }), ["cardiology", "rayfin", "databricks"])


class FreshDatabricksExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_export_does_not_run_when_snapshot_cleanup_fails(self):
        runner = object.__new__(addons.AddonRunner)
        runner.config = {"resource_group_name": "rg", "expected_subscription_id": "subscription"}
        runner.env = {}
        runner.working_copy = Mock(return_value=Path("unused"))
        runner.resource = Mock(return_value={"id": "fhir-id"})
        exported = False
        async def step(title, *_args, **_kwargs):
            nonlocal exported
            if title == "Empty previous Databricks export":
                raise RuntimeError("Snapshot directory deletion denied")
            exported = True
        runner.ps = AsyncMock(side_effect=step)
        with patch.object(addons, "az_json", return_value={"properties": {"exportConfiguration": {"storageAccountName": "exports"}}}), \
             patch.dict(sys.modules, {"yaml": Mock()}):
            with self.assertRaisesRegex(RuntimeError, "Snapshot directory deletion denied"):
                await runner.databricks(fresh_export=True)
        self.assertFalse(exported, "An export must not mix new files into a snapshot that failed cleanup")

    async def test_disabled_automatic_identity_management_is_an_actionable_failure(self):
        runner = object.__new__(addons.AddonRunner)
        runner.command = AsyncMock(side_effect=RuntimeError(
            "Provision Entra group g: Error: Automatic Identity Management is not enabled for account 1."))
        with self.assertRaisesRegex(RuntimeError, "Automatic Identity Management is off .* base deployment is unaffected"):
            await runner.ensure_admin_group({}, Path("unused"), "object-id", "g")
        runner.command.assert_awaited_once()
        self.assertEqual(runner.command.await_args.args[1][:3], ["databricks", "workspace-iam-v2", "resolve-group-proxy"])

    async def test_other_group_provisioning_errors_are_not_rewritten(self):
        runner = object.__new__(addons.AddonRunner)
        runner.command = AsyncMock(side_effect=RuntimeError("Provision Entra group g: permission denied"))
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            await runner.ensure_admin_group({}, Path("unused"), "object-id", "g")

    async def test_alert_recipient_that_is_not_a_workspace_user_is_dropped_not_passed_to_the_bundle(self):
        runner = object.__new__(addons.AddonRunner)
        runner.log = Mock()
        runner.command = AsyncMock(return_value="[]")
        self.assertEqual(await runner.databricks_alert_recipient({}, Path("unused"), "alerts@example.com"), "")
        runner.log.assert_called_once()
        self.assertIn('userName eq "alerts@example.com"', runner.command.await_args.args[1])

    async def test_alert_recipient_that_is_a_workspace_user_is_kept(self):
        runner = object.__new__(addons.AddonRunner)
        runner.log = Mock()
        runner.command = AsyncMock(return_value='[{"userName": "joey@example.com"}]')
        self.assertEqual(await runner.databricks_alert_recipient({}, Path("unused"), "joey@example.com"), "joey@example.com")

    async def test_empty_alert_recipient_makes_no_lookup(self):
        runner = object.__new__(addons.AddonRunner)
        runner.command = AsyncMock()
        self.assertEqual(await runner.databricks_alert_recipient({}, Path("unused"), ""), "")
        runner.command.assert_not_awaited()

    async def test_new_databricks_workspace_is_assigned_without_the_optional_azure_cli_extension(self):
        runner = object.__new__(addons.AddonRunner)
        runner.config = {"resource_group_name": "rg", "expected_subscription_id": "subscription", "location": "westus2"}
        runner.azure = []
        runner.command = AsyncMock(side_effect=[
            RuntimeError("No metastore assigned"),
            '[{"metastore_id":"metastore","region":"westus2"}]',
            "",
            '{"metastore_id":"metastore"}',
        ])

        def az(_config, *args):
            if args[:2] == ("resource", "list"):
                return [{"id": "/subscriptions/subscription/resourceGroups/rg/providers/Microsoft.Databricks/workspaces/new"}]
            if args[:2] == ("resource", "show"):
                return {"properties": {"workspaceId": "7405609633265528"}}
            raise AssertionError(args)

        with patch.object(addons, "az_json", side_effect=az):
            await runner.ensure_metastore({}, Path("unused"))

        assignment = runner.command.await_args_list[2].args[1]
        self.assertEqual(assignment[:5], ["databricks", "metastores", "assign", "7405609633265528", "metastore"])

    async def test_a_failing_addon_does_not_prevent_the_others_from_running(self):
        runner = object.__new__(addons.AddonRunner)
        runner.deployment = {"customStatus": {}, "output": {"phases": [], "resources": {}}}
        runner.discover, runner.persist, runner.log = AsyncMock(), Mock(), Mock()
        ran = []
        async def databricks(fresh_export=False): raise RuntimeError("bundle invalid")
        async def rayfin(fresh_export=False): ran.append("rayfin"); return {"ok": 1}
        async def cardiology(fresh_export=False): ran.append("cardiology"); return {"ok": 2}
        runner.databricks, runner.rayfin, runner.cardiology = databricks, rayfin, cardiology
        with self.assertRaisesRegex(RuntimeError, "databricks: bundle invalid"):
            await runner.run(["databricks", "rayfin", "cardiology"])
        self.assertEqual(ran, ["rayfin", "cardiology"])
        states = {k: v["status"] for k, v in runner.deployment["customStatus"]["addons"].items()}
        self.assertEqual(states, {"databricks": "failed", "rayfin": "succeeded", "cardiology": "succeeded"})

    async def test_cardiology_base_eventstream_is_resumed_before_use(self):
        runner = object.__new__(addons.AddonRunner)
        runner.ws = "workspace"
        runner.items = [{"type": "Eventstream", "displayName": "MasimoTelemetryStream", "id": "stream"}]
        runner.substep = Mock()
        runner.cloud = Mock()
        runner.cloud.call = Mock(side_effect=[
            {"sources": [{"name": "source", "status": "Paused"}],
             "destinations": [{"name": "destination", "status": "Paused"}]},
            {},
            {"sources": [{"name": "source", "status": "Resuming"}],
             "destinations": [{"name": "destination", "status": "Running"}]},
            {"sources": [{"name": "source", "status": "Running"}],
             "destinations": [{"name": "destination", "status": "Running"}]},
        ])

        with patch.object(addons.asyncio, "sleep", new=AsyncMock()) as sleep:
            await runner.ensure_eventstream_running("MasimoTelemetryStream")

        resume = runner.cloud.call.call_args_list[1].args
        self.assertEqual(resume[:5], (
            "POST",
            addons.FABRIC + "/v1/workspaces/workspace/eventstreams/stream/resume",
            addons.FABRIC,
            {"startType": "WhenLastStopped"},
            "eventstream-cli",
        ))
        sleep.assert_awaited_once_with(10)
        runner.substep.assert_any_call("Resume MasimoTelemetryStream", "succeeded")

    async def test_cancelling_the_deployment_stops_remaining_addons(self):
        runner = object.__new__(addons.AddonRunner)
        runner.deployment = {"customStatus": {}, "output": {"phases": [], "resources": {}}, "runtimeStatus": "Terminated"}
        runner.discover, runner.persist, runner.log = AsyncMock(), Mock(), Mock()
        async def databricks(fresh_export=False): raise RuntimeError("Add-on cancelled")
        runner.databricks, runner.rayfin = databricks, AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            await runner.run(["databricks", "rayfin"])
        runner.rayfin.assert_not_awaited()


class BundlePreparationTests(unittest.TestCase):
    def test_every_production_target_of_the_real_bundle_gets_a_user_root_path_and_no_service_principal(self):
        import yaml
        bundle = yaml.safe_load((addons.ROOT / "azure-databricks/implementation/bundle/databricks.yml").read_text())
        production = [n for n, t in bundle["targets"].items() if t.get("mode") == "production"]
        self.assertTrue(production, "the bundle must still have production targets for this test to mean anything")
        addons.prepare_bundle(bundle, "joey@example.com")
        for name, target in bundle["targets"].items():
            self.assertNotIn("run_as", target)
            expected = "/Workspace/Users/joey@example.com/.bundle/${bundle.name}/${bundle.target}"
            self.assertEqual(target.get("workspace", {}).get("root_path"), expected if name in production else None)


if __name__ == "__main__":
    unittest.main()
