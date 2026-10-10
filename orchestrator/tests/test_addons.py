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


    def test_selection_does_not_add_unrequested_services(self):
        self.assertEqual(addons.selected({"deploy_rayfin_apps": True}), ["rayfin"])
        self.assertEqual(addons.selected({}), [])


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


if __name__ == "__main__":
    unittest.main()
