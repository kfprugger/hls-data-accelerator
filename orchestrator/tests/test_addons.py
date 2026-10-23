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

    def test_selection_does_not_add_unrequested_services(self):
        self.assertEqual(addons.selected({"deploy_rayfin_apps": True}), ["rayfin"])
        self.assertEqual(addons.selected({}), [])


class FreshDatabricksExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_export_resets_destination_before_export(self):
        for remaining in ([], ["stale.ndjson"]):
            with self.subTest(remaining=remaining):
                runner = object.__new__(addons.AddonRunner)
                runner.config = {"resource_group_name": "rg", "expected_subscription_id": "subscription"}
                runner.env = {}
                runner.working_copy = Mock(return_value=Path("unused"))
                runner.resource = Mock(return_value={"id": "fhir-id"})
                events = []
                def azure(_config, *args):
                    events.append(args)
                    if args[:2] == ("resource", "show"):
                        return {"properties": {"exportConfiguration": {"storageAccountName": "exports"}}}
                    if args[:3] == ("storage", "blob", "list"):
                        return remaining
                    return {}
                async def command(_title, args, **kwargs):
                    events.append(tuple(args))
                    self.assertEqual(kwargs["env"]["AZCOPY_AUTO_LOGIN_TYPE"], "AZCLI")
                async def export(*args):
                    events.append(("export",))
                    raise RuntimeError("export reached")
                runner.command = AsyncMock(side_effect=command)
                runner.ps = AsyncMock(side_effect=export)
                # This reset-only test stops at export, before the optional YAML bundle work.
                with patch.object(addons, "az_json", side_effect=azure), patch.dict(sys.modules, {"yaml": Mock()}):
                    with self.assertRaisesRegex(RuntimeError, "not empty" if remaining else "export reached"):
                        await runner.databricks(fresh_export=True)
                self.assertEqual(events[1][:3], ("storage", "container", "create"))
                self.assertEqual(events[2][:3], ("azcopy", "remove", "https://exports.blob.core.windows.net/fhir-export-databricks/*"))
                self.assertEqual(events[3][:3], ("storage", "blob", "list"))
                self.assertEqual(runner.ps.await_count, 0 if remaining else 1)


if __name__ == "__main__":
    unittest.main()
