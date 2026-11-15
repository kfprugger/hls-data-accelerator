"""Offline checks for the hosted sandbox trust boundary and device-code contract."""
import asyncio
import errno
import importlib.util
import json
import logging
import os
import sqlite3
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared import hosted


class HostedGuardTests(unittest.IsolatedAsyncioTestCase):
    async def response(self, path, method="GET", key=""):
        async def downstream(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        sent = []
        async def send(message):
            sent.append(message)
        async def receive():
            return {"type": "http.request", "body": b""}
        with patch.object(hosted, "HOSTED", True), patch.dict(os.environ, {"HLS_GATEWAY_KEY": "private-key"}):
            await hosted.GatewayGuard(downstream)({"type": "http", "path": path, "method": method,
                "headers": [(b"x-hls-gateway-key", key.encode())]}, receive, send)
        return sent[0]["status"]

    async def test_only_get_health_bypasses_gateway_key(self):
        self.assertEqual(await self.response("/api/health"), 204)
        for path, method in [("/", "GET"), ("/api/hosted/whoami", "GET"), ("/api/auth/state", "GET"), ("/api/auth/target", "PUT"), ("/api/auth/device-login/flow/cancel", "POST"), ("/api/health", "POST"), ("/api/deploy/a/logs/stream", "GET")]:
            self.assertEqual(await self.response(path, method), 403)
            self.assertEqual(await self.response(path, method, "wrong-key"), 403)
            self.assertEqual(await self.response(path, method, "private-key"), 204)

    async def test_background_activity_probe_does_not_extend_idle(self):
        before = hosted._last_activity
        await self.response("/api/hosted/activity", key="private-key")
        self.assertEqual(hosted._last_activity, before)
        await self.response("/api/deployments", key="private-key")
        self.assertNotEqual(hosted._last_activity, before)


class DeviceCodeTests(unittest.IsolatedAsyncioTestCase):
    async def login(self, tool, output, returncode=0):
        process = AsyncMock()
        process.stdout = asyncio.StreamReader()
        process.stdout.feed_data(output.encode())
        process.stdout.feed_eof()
        process.returncode = returncode
        session = {"status": "pending", "ready": asyncio.Event()}
        req = hosted.DeviceLoginRequest(tenant_id="11111111-1111-1111-1111-111111111111",
            subscription_id="22222222-2222-2222-2222-222222222222", tool=tool)
        run = AsyncMock(side_effect=["", "", '{"tenantId":"11111111-1111-1111-1111-111111111111"}'])
        with patch.object(hosted, "_run", run), patch.object(asyncio, "create_subprocess_exec", AsyncMock(return_value=process)) as create:
            await hosted._device_login(session, req, lambda: None)
        return session, create.call_args.args, run

    async def test_az_uses_device_code_and_selects_subscription(self):
        session, args, run = await self.login("az", "To sign in, use https://microsoft.com/devicelogin and enter the code ABCD12345 to authenticate.")
        self.assertEqual(session["status"], "succeeded")
        self.assertEqual(session["user_code"], "ABCD12345")
        self.assertEqual(args[:3], ("az", "login", "--use-device-code"))
        self.assertIn("--allow-no-subscriptions", args)
        self.assertEqual(run.call_args_list[1].args[:3], ("az", "account", "set"))

    async def test_current_cli_device_url_exposes_code_to_user(self):
        session, _, _ = await self.login("az", "To sign in, use a web browser to open the page https://login.microsoft.com/device and enter the code E4AAFX9VN to authenticate.")
        self.assertTrue(session["ready"].is_set())
        self.assertEqual(session["verification_uri"], "https://login.microsoft.com/device")
        self.assertEqual(session["user_code"], "E4AAFX9VN")

    async def test_azps_parses_warning_and_persists_context(self):
        session, args, _ = await self.login("azps", "WARNING: To sign in, use https://microsoft.com/devicelogin and enter the code XYZA12345 to authenticate.")
        self.assertEqual(session["status"], "succeeded")
        self.assertEqual(session["user_code"], "XYZA12345")
        for fragment in ["Connect-AzAccount -UseDeviceAuthentication", "Enable-AzContextAutosave -Scope CurrentUser", "Set-AzContext -Tenant"]:
            self.assertIn(fragment, args[-1])

    async def test_conditional_access_failure_has_actionable_hint(self):
        for error in ["AADSTS53003", "AADSTS530033", "AADSTS50097", "blocked by Conditional Access", "device code flow is blocked"]:
            session, _, _ = await self.login("az", error, 1)
            self.assertEqual(session["status"], "failed")
            self.assertIn("tenant blocks device-code", session["error_hint"])
            self.assertIn("run the deployer locally", session["error_hint"])


class AuthenticationRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        environment = patch.dict(os.environ, {"HLS_DATA_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.store = self.load_store()
        modules = patch.dict(sys.modules, {"shared.database": self.store})
        modules.start()
        self.addCleanup(modules.stop)
        sessions = patch.dict(hosted._sessions, {}, clear=True)
        sessions.start()
        self.addCleanup(sessions.stop)
        self.target = {"tenant_id": "11111111-1111-1111-1111-111111111111",
                       "subscription_id": "22222222-2222-2222-2222-222222222222"}
        self.active = 0
        self.app = FastAPI()
        hosted.install_hosted_routes(self.app, lambda: self.active, lambda: None)

    def load_store(self):
        path = Path(__file__).resolve().parents[1] / "shared" / "database.py"
        spec = importlib.util.spec_from_file_location("refresh_database_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch("atexit.register"):
            spec.loader.exec_module(module)
        self.addCleanup(module.shutdown_database)
        self.addCleanup(module.get_db().close)
        return module

    def endpoint(self, path):
        return next(route.endpoint for route in self.app.routes if route.path == path)

    async def test_target_survives_restart_without_persisting_device_codes(self):
        await self.endpoint("/api/auth/target")(hosted.DeploymentTarget(**self.target))
        self.store.backup_database()
        self.store.shutdown_database()
        restored = self.load_store()
        with patch.dict(sys.modules, {"shared.database": restored}):
            state = await self.endpoint("/api/auth/state")()
        self.assertEqual(state, {"target": self.target, "pending": None})
        with sqlite3.connect(self.directory / "orchestrator.db") as db:
            saved = db.execute("SELECT value FROM form_history WHERE field='deployment-auth-target'").fetchone()[0]
        db.close()
        self.assertEqual(json.loads(saved), self.target)

    async def test_refresh_resumes_same_code_with_original_expiration(self):
        await self.endpoint("/api/auth/target")(hosted.DeploymentTarget(**self.target))
        hosted._sessions["flow"] = {"status": "pending", "tool": "azps", "target": self.target,
            "created": 100, "user_code": "RESTORE123", "verification_uri": "https://login.microsoft.com/device",
            "process": object(), "token": "must-not-be-returned"}
        with patch.object(hosted.time, "monotonic", return_value=160):
            first = await self.endpoint("/api/auth/state")()
        with patch.object(hosted.time, "monotonic", return_value=190):
            second = await self.endpoint("/api/auth/state")()
        self.assertEqual(first["pending"]["session_id"], "flow")
        self.assertEqual(first["pending"]["user_code"], "RESTORE123")
        self.assertEqual(second["pending"]["user_code"], "RESTORE123")
        self.assertEqual(first["pending"]["expires_in"], 840)
        self.assertEqual(second["pending"]["expires_in"], 810)
        self.assertNotIn("token", second["pending"])
        self.assertNotIn("process", second["pending"])

    async def test_expired_code_no_longer_blocks_target_selection(self):
        hosted._sessions["flow"] = {"status": "pending", "tool": "az", "target": self.target,
                                   "created": 100, "user_code": "EXPIRED123"}
        with patch.object(hosted.time, "monotonic", return_value=1000):
            state = await self.endpoint("/api/auth/state")()
        self.assertIsNone(state["pending"])
        self.assertEqual(hosted._sessions["flow"]["status"], "failed")
        self.assertEqual(await self.endpoint("/api/auth/target")(hosted.DeploymentTarget(**self.target)), self.target)

    async def test_active_run_accepts_the_saved_target_but_rejects_a_change(self):
        endpoint = self.endpoint("/api/auth/target")
        target = hosted.DeploymentTarget(**self.target)
        await endpoint(target)
        self.active = 1
        self.assertEqual(await endpoint(target), self.target)
        changed = hosted.DeploymentTarget(**{**self.target, "subscription_id": "33333333-3333-3333-3333-333333333333"})
        with self.assertRaises(HTTPException) as error:
            await endpoint(changed)
        self.assertEqual(error.exception.status_code, 409)

    async def test_cancel_stops_only_pending_task_without_touching_other_tool_cache(self):
        cache = self.directory / "other-tool-token-cache"
        cache.write_text("existing-authenticated-session")
        task = asyncio.create_task(asyncio.Event().wait())
        await asyncio.sleep(0)
        hosted._sessions["flow"] = {"status": "pending", "task": task, "tool": "az", "target": self.target}
        with patch.object(hosted, "_run", side_effect=AssertionError("Cancellation must not clear Azure account caches")):
            result = await self.endpoint("/api/auth/device-login/{session_id}/cancel")("flow")
        self.assertEqual(result, {"status": "cancelled"})
        self.assertTrue(task.cancelled())
        self.assertEqual(hosted._sessions["flow"]["status"], "failed")
        self.assertEqual(cache.read_text(), "existing-authenticated-session")
        self.assertEqual(await self.endpoint("/api/auth/device-login/{session_id}/cancel")("flow"), result)

    async def test_cancel_cannot_invalidate_completed_sign_in(self):
        hosted._sessions["flow"] = {"status": "succeeded", "account": {"tenantId": self.target["tenant_id"]}}
        with self.assertRaises(HTTPException) as error:
            await self.endpoint("/api/auth/device-login/{session_id}/cancel")("flow")
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(hosted._sessions["flow"]["status"], "succeeded")

    async def test_cancel_refuses_when_deployment_is_active(self):
        self.active = 1
        hosted._sessions["flow"] = {"status": "pending"}
        with self.assertRaises(HTTPException) as error:
            await self.endpoint("/api/auth/device-login/{session_id}/cancel")("flow")
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(hosted._sessions["flow"]["status"], "pending")


class PersistentDatabaseTests(unittest.TestCase):
    def load_database(self):
        path = Path(__file__).resolve().parents[1] / "shared" / "database.py"
        spec = importlib.util.spec_from_file_location("sandbox_database_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch("atexit.register"):
            spec.loader.exec_module(module)
        self.addCleanup(module.shutdown_database)
        self.addCleanup(module.get_db().close)
        return module

    def test_local_wal_snapshot_and_restore_include_form_history(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HLS_DATA_DIR": directory}):
            connect = sqlite3.connect
            def local_connect(path, *args, **kwargs):
                self.assertNotEqual(Path(path).parent, Path(directory), "SQLite must never open files on SMB")
                return connect(path, *args, **kwargs)
            with patch.object(sqlite3, "connect", side_effect=local_connect):
                db = self.load_database()
                self.assertNotEqual(db.DB_PATH.parent, Path(directory))
                db.add_form_history("workspace", "my-workspace")
                db.save_deployment("run-1", {"runtimeStatus": "Completed"})
                db.backup_database()
                self.assertTrue((Path(directory) / "orchestrator.db").is_file())
                self.assertFalse((Path(directory) / "orchestrator.db.tmp").exists())
                db.shutdown_database()
                restored = self.load_database()
                self.assertEqual(restored.get_form_history("workspace"), ["my-workspace"])
                self.assertEqual(restored.get_deployment("run-1")["runtimeStatus"], "Completed")
                restored.shutdown_database()
            with connect(str(Path(directory) / "orchestrator.db")) as snapshot:
                self.assertEqual(snapshot.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            snapshot.close()

    def test_interrupted_addon_preserves_completed_base_and_releases_pending_run(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HLS_DATA_DIR": directory}):
            db = self.load_database()
            db.save_deployment("base", {"runtimeStatus": "Running", "customStatus": {
                "addonRunBaseCompleted": True, "addons": {"databricks": {"status": "paused"}}},
                "output": {"phases": [{"phase": "Add-on: Databricks", "status": "running"}]}})
            db.save_deployment("pending", {"runtimeStatus": "Pending"})
            db.mark_stale_as_terminated()
            restored = db.get_deployment("base")
            self.assertEqual(restored["runtimeStatus"], "Completed")
            self.assertEqual(restored["customStatus"]["addons"]["databricks"]["status"], "failed")
            self.assertEqual(restored["output"]["phases"][0]["status"], "failed")
            self.assertEqual(db.get_deployment("pending")["runtimeStatus"], "Terminated")
            db.shutdown_database()


    def test_backfill_and_state_tracking_reconcile_and_peer_target_import(self):
        with tempfile.TemporaryDirectory() as shared_root_str:
            shared_root = Path(shared_root_str)
            peer_dir = shared_root / "9da330f25845"
            active_dir = shared_root / "398c6e793157"
            peer_dir.mkdir(parents=True)
            active_dir.mkdir(parents=True)

            target_tid = "33333333-3333-4333-8333-333333333333"
            target_sub = "44444444-4444-4444-8444-444444444444"

            # 1. Populate peer sandbox (9da330f25845) with a completed deployment and a state-tracking ledger
            with patch.dict(os.environ, {"HLS_DATA_DIR": str(peer_dir), "HLS_SHARED_DATA_DIR": str(shared_root)}):
                peer_db = self.load_database()
                peer_dep = {
                    "name": "deploy_all_orchestrator",
                    "runtimeStatus": "Completed",
                    "createdTime": "2026-10-25T16:39:43+00:00",
                    "lastUpdatedTime": "2026-10-25T18:10:00+00:00",
                    "customStatus": {
                        "status": "succeeded",
                        "workspaceName": "med-1024",
                        "resourceGroupName": "rg-med-1024",
                        "capacityName": "fabrjbwu2",
                        "deployConfig": {
                            "expected_tenant_id": target_tid,
                            "expected_subscription_id": target_sub,
                            "fabric_workspace_name": "med-1024",
                            "resource_group_name": "rg-med-1024",
                            "location": "westus2",
                            "admin_security_group": "sg-azure-admins",
                            "alert_email": "alerts@example.com",
                            "payer_ops_email": "ops@example.com",
                            "deploy_cardiology": True,
                            "cardiology_location": "eastus2",
                            "cardiology_prefix": "cardio1024",
                            "cardiology_app_users": ["user@example.com", "alerts@example.com"],
                        },
                    },
                }
                peer_db.save_deployment("P1234567-20261025-163943", peer_dep)
                peer_db.backfill_form_history_from_deployments()
                self.assertEqual(peer_db.get_form_history("naming-prefix"), ["med-1024"])
                self.assertEqual(peer_db.get_form_history("cardiology-prefix"), ["cardio1024"])
                self.assertEqual(set(peer_db.get_form_history("cardiology-app-users")), {"user@example.com", "alerts@example.com"})

                # Also write a state-tracking ledger for med-1009 that was not yet in deployments table
                peer_tracking = peer_dir / "state-tracking"
                peer_tracking.mkdir(parents=True, exist_ok=True)
                (peer_tracking / ".deployment-state-med-1009.json").write_text(json.dumps({
                    "phases": [{
                        "phase": "Phase1+2+3+4+5+6+7",
                        "timestamp": "2026-10-10T00:00:10Z",
                        "resources": {"ResourceGroupName": "rg-med-1009", "FabricWorkspaceName": "med-1009", "Location": "westus2"},
                        "steps": [{"name": "Phase 1: Fabric Workspace", "success": True, "duration": "0.2 min"}],
                    }]
                }))
                peer_db.backup_database()
                peer_db.shutdown_database()

            # 2. Start active sandbox (398c6e793157) and verify peer history is NOT imported for an unrelated subscription
            with patch.dict(os.environ, {"HLS_DATA_DIR": str(active_dir), "HLS_SHARED_DATA_DIR": str(shared_root)}):
                active_db = self.load_database()
                unrelated = active_db.import_target_history_from_shared_storage(
                    "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
                )
                self.assertEqual(unrelated["importedDeployments"], 0)
                self.assertEqual(len(active_db.list_deployments()), 0)

                # 3. Now authenticate to the matching (target_tid, target_sub) and verify runs + ledgers + form_history import
                imported = active_db.import_target_history_from_shared_storage(target_tid, target_sub)
                self.assertEqual(imported["importedDeployments"], 1)
                self.assertEqual(imported["reconstructedLedgers"], 1)
                workspaces = {d["customStatus"]["workspaceName"] for d in active_db.list_deployments()}
                self.assertEqual(workspaces, {"med-1024", "med-1009"})
                self.assertIn("med-1024", active_db.get_form_history("naming-prefix"))
                self.assertEqual(active_db.get_form_history("admin-security-group"), ["sg-azure-admins"])
                self.assertEqual(active_db.get_form_history("cardiology-prefix"), ["cardio1024"])
                active_db.shutdown_database()

    def test_encrypted_azure_auth_seal_roundtrip_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as data_dir_str, tempfile.TemporaryDirectory() as cli_dir_str:
            data_dir = Path(data_dir_str)
            cli_dir = Path(cli_dir_str)
            def populate_cli():
                (cli_dir / "azureProfile.json").write_text(json.dumps({
                    "subscriptions": [{"id": "11111111-2222-3333-4444-555555555555", "tenantId": "33333333-3333-4333-8333-333333333333", "isDefault": True}]
                }))
                (cli_dir / "msal_token_cache.json").write_text(json.dumps({
                    "AccessToken": {"at-1": {"secret": "must-be-stripped"}},
                    "IdToken": {"id-1": {"secret": "must-be-stripped"}},
                    "RefreshToken": {"rt-1": {"secret": "refresh-secret-value"}},
                    "Account": {"acct-1": {"username": "user@example.com"}},
                    "AppMetadata": {},
                }))
            populate_cli()
            env = {
                "HLS_DATA_DIR": data_dir_str,
                "AZURE_CONFIG_DIR": cli_dir_str,
                "HLS_GATEWAY_KEY": "gateway-secret-key-for-user",
                "HLS_SANDBOX_USER_TID": "33333333-3333-4333-8333-333333333333",
                "HLS_SANDBOX_USER_OID": "55555555-5555-4555-8555-555555555555",
            }
            with patch.dict(os.environ, env):
                self.assertTrue(hosted.seal_azure_auth_cache())
                seal_file = data_dir / ".encrypted-azure-auth.bin"
                self.assertTrue(seal_file.is_file())
                raw_seal = seal_file.read_bytes()
                self.assertNotIn(b"refresh-secret-value", raw_seal)
                self.assertNotIn(b"must-be-stripped", raw_seal)

                # Same sandbox container re-reads its seal with its own gateway key
                for f in cli_dir.iterdir():
                    f.unlink()
                self.assertFalse((cli_dir / "msal_token_cache.json").exists())
                self.assertTrue(hosted.restore_azure_auth_cache())
                restored_msal = json.loads((cli_dir / "msal_token_cache.json").read_text())
                self.assertEqual(restored_msal["AccessToken"], {})
                self.assertEqual(restored_msal["IdToken"], {})
                self.assertEqual(restored_msal["RefreshToken"]["rt-1"]["secret"], "refresh-secret-value")

                # Another sandbox with a different gateway key cannot decrypt and deletes the unreadable seal
                for f in cli_dir.iterdir():
                    f.unlink()
                with patch.dict(os.environ, {"HLS_GATEWAY_KEY": "different-sandbox-gateway-key"}):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                    self.assertFalse((cli_dir / "msal_token_cache.json").exists())
                    self.assertFalse(seal_file.exists())

                # Re-populate and re-seal before testing wrong user identity
                populate_cli()
                self.assertTrue(hosted.seal_azure_auth_cache())
                self.assertTrue(seal_file.is_file())
                for f in cli_dir.iterdir():
                    f.unlink()
                with patch.dict(os.environ, {"HLS_SANDBOX_USER_OID": "00000000-0000-0000-0000-000000000000"}):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                    self.assertFalse((cli_dir / "msal_token_cache.json").exists())
                    self.assertFalse(seal_file.exists())

                # Verify logout clears the seal
                populate_cli()
                self.assertTrue(hosted.seal_azure_auth_cache())
                self.assertTrue(seal_file.is_file())
                hosted.clear_azure_auth_seal()
                self.assertFalse(seal_file.exists())

    def test_legacy_version1_seal_rejected_and_unlinked_and_sweep_behavior(self):
        import hashlib
        import zlib
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        with tempfile.TemporaryDirectory() as data_dir_str, tempfile.TemporaryDirectory() as cli_dir_str:
            data_dir = Path(data_dir_str)
            cli_dir = Path(cli_dir_str)
            tid = "33333333-3333-4333-8333-333333333333"
            oid = "55555555-5555-4555-8555-555555555555"
            env = {
                "HLS_DATA_DIR": data_dir_str,
                "AZURE_CONFIG_DIR": cli_dir_str,
                "HLS_GATEWAY_KEY": "gateway-secret-key-for-user",
                "HLS_SANDBOX_USER_TID": tid,
                "HLS_SANDBOX_USER_OID": oid,
            }
            with patch.dict(os.environ, env):
                # Only a single current gateway-key-bound key is derived
                self.assertEqual(len(hosted._derive_seal_keys()), 1)

                # (i) Legacy version-1 seal written with old tid:oid key
                identity = f"{tid}:{oid}".encode("utf-8")
                salt = hashlib.sha256(identity).digest()
                legacy_key = hosted._hkdf(f"hls-seal-v2:{tid}:{oid}".encode("utf-8"), salt, b"hls-sandbox-azure-auth-seal-v1")
                payload_v1 = {
                    "version": 1,
                    "azureProfile": {"subscriptions": []},
                    "msalTokenCache": {"RefreshToken": {"rt-1": {"secret": "legacy-secret"}}},
                }
                plaintext_v1 = zlib.compress(json.dumps(payload_v1).encode("utf-8"))
                nonce_v1 = os.urandom(12)
                ciphertext_v1 = AESGCM(legacy_key).encrypt(nonce_v1, plaintext_v1, b"hls-azure-auth-v1")
                seal_file = data_dir / ".encrypted-azure-auth.bin"
                seal_file.write_bytes(b"HLS1" + nonce_v1 + ciphertext_v1)
                self.assertTrue(seal_file.is_file())

                # Restore returns False, MSAL cache is not restored, and the legacy seal is deleted
                self.assertFalse(hosted.restore_azure_auth_cache())
                self.assertFalse((cli_dir / "msal_token_cache.json").exists())
                self.assertFalse(seal_file.exists())

                # (ii) Current version-2 seal restores
                (cli_dir / "azureProfile.json").write_text(json.dumps({
                    "subscriptions": [{"id": "11111111-2222-3333-4444-555555555555", "tenantId": tid, "isDefault": True}]
                }))
                (cli_dir / "msal_token_cache.json").write_text(json.dumps({
                    "AccessToken": {},
                    "IdToken": {},
                    "RefreshToken": {"rt-1": {"secret": "v2-refresh-secret"}},
                    "Account": {"acct-1": {"username": "user@example.com"}},
                    "AppMetadata": {},
                }))
                self.assertTrue(hosted.seal_azure_auth_cache())
                self.assertTrue(seal_file.is_file())
                for f in cli_dir.iterdir():
                    f.unlink()
                self.assertTrue(hosted.restore_azure_auth_cache())
                self.assertTrue((cli_dir / "msal_token_cache.json").exists())
                restored = json.loads((cli_dir / "msal_token_cache.json").read_text())
                self.assertEqual(restored["RefreshToken"]["rt-1"]["secret"], "v2-refresh-secret")

                # (iv) Missing keys do not delete the seal
                for f in cli_dir.iterdir():
                    f.unlink()
                with patch.dict(os.environ, {"HLS_GATEWAY_KEY": ""}):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                    self.assertTrue(seal_file.exists())
                with patch.dict(os.environ, {"HLS_SANDBOX_USER_TID": ""}):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                    self.assertTrue(seal_file.exists())

                # (iii) Sweep deletes peer's legacy seal and keeps version-2 seal
                with tempfile.TemporaryDirectory() as shared_root_str:
                    shared_root = Path(shared_root_str)
                    peer_legacy = shared_root / "peer_legacy"
                    peer_legacy.mkdir()
                    (peer_legacy / ".encrypted-azure-auth.bin").write_bytes(b"HLS1" + nonce_v1 + ciphertext_v1)

                    peer_v2 = shared_dir_v2 = shared_root / "peer_v2"
                    peer_v2.mkdir()
                    (peer_v2 / ".encrypted-azure-auth.bin").write_bytes(seal_file.read_bytes())

                    peer_corrupt = shared_root / "peer_corrupt"
                    peer_corrupt.mkdir()
                    (peer_corrupt / ".encrypted-azure-auth.bin").write_bytes(b"corrupt-data")

                    sweep_stats = hosted.sweep_legacy_azure_auth_seals(shared_root)
                    self.assertEqual(sweep_stats["scanned"], 3)
                    self.assertEqual(sweep_stats["kept"], 1)
                    self.assertEqual(sweep_stats["deleted"], 2)
                    self.assertFalse((peer_legacy / ".encrypted-azure-auth.bin").exists())
                    self.assertFalse((peer_corrupt / ".encrypted-azure-auth.bin").exists())
                    self.assertTrue((peer_v2 / ".encrypted-azure-auth.bin").exists())

    def test_seal_read_failure_preserves_cache_and_protects_peers(self):
        with tempfile.TemporaryDirectory() as data_dir_str, tempfile.TemporaryDirectory() as cli_dir_str:
            data_dir = Path(data_dir_str)
            cli_dir = Path(cli_dir_str)
            tid = "33333333-3333-4333-8333-333333333333"
            oid = "55555555-5555-4555-8555-555555555555"
            env = {
                "HLS_DATA_DIR": data_dir_str,
                "AZURE_CONFIG_DIR": cli_dir_str,
                "HLS_GATEWAY_KEY": "gateway-secret-key-for-user",
                "HLS_SANDBOX_USER_TID": tid,
                "HLS_SANDBOX_USER_OID": oid,
            }
            with patch.dict(os.environ, env):
                (cli_dir / "azureProfile.json").write_text(json.dumps({
                    "subscriptions": [{"id": "11111111-2222-3333-4444-555555555555", "tenantId": tid, "isDefault": True}]
                }))
                (cli_dir / "msal_token_cache.json").write_text(json.dumps({
                    "AccessToken": {},
                    "IdToken": {},
                    "RefreshToken": {"rt-1": {"secret": "v2-refresh-secret"}},
                    "Account": {"acct-1": {"username": "user@example.com"}},
                    "AppMetadata": {},
                }))
                self.assertTrue(hosted.seal_azure_auth_cache())
                seal_file = data_dir / ".encrypted-azure-auth.bin"
                self.assertTrue(seal_file.is_file())
                original_seal_bytes = seal_file.read_bytes()

                # 1. Own read failure: restore_azure_auth_cache must warn and return False,
                # leaving the seal file intact and CLI credentials unrestored.
                for f in cli_dir.iterdir():
                    f.unlink()
                self.assertFalse((cli_dir / "msal_token_cache.json").exists())

                real_read_bytes = Path.read_bytes
                def mock_read_bytes(path_obj, *args, **kwargs):
                    if path_obj.resolve() == seal_file.resolve():
                        raise OSError("SMB transient read failure")
                    return real_read_bytes(path_obj, *args, **kwargs)

                with patch.object(Path, "read_bytes", mock_read_bytes):
                    self.assertFalse(hosted.restore_azure_auth_cache())

                # Seal survived unchanged
                self.assertTrue(seal_file.exists())
                self.assertEqual(seal_file.read_bytes(), original_seal_bytes)
                # CLI credentials not restored
                self.assertFalse((cli_dir / "msal_token_cache.json").exists())
                self.assertFalse((cli_dir / "azureProfile.json").exists())

                # After transient read error clears, restore succeeds and restores credentials
                self.assertTrue(hosted.restore_azure_auth_cache())
                self.assertTrue((cli_dir / "msal_token_cache.json").exists())
                restored = json.loads((cli_dir / "msal_token_cache.json").read_text())
                self.assertEqual(restored["RefreshToken"]["rt-1"]["secret"], "v2-refresh-secret")

                # 2. Peer read failures and sweep behavior
                with tempfile.TemporaryDirectory() as shared_root_str:
                    shared_root = Path(shared_root_str)

                    # Peer with valid HLS2 seal that hits a transient read failure
                    peer_transient = shared_root / "peer_transient"
                    peer_transient.mkdir()
                    seal_transient = peer_transient / ".encrypted-azure-auth.bin"
                    seal_transient.write_bytes(original_seal_bytes)

                    # Peer with verified legacy header (HLS1)
                    peer_legacy = shared_root / "peer_legacy"
                    peer_legacy.mkdir()
                    seal_legacy = peer_legacy / ".encrypted-azure-auth.bin"
                    seal_legacy.write_bytes(b"HLS1" + os.urandom(28))

                    # Peer with verified corrupt 4-byte header
                    peer_corrupt = shared_root / "peer_corrupt"
                    peer_corrupt.mkdir()
                    seal_corrupt = peer_corrupt / ".encrypted-azure-auth.bin"
                    seal_corrupt.write_bytes(b"BAD0" + os.urandom(28))

                    # Peer with incomplete header (< 4 bytes)
                    peer_truncated = shared_root / "peer_truncated"
                    peer_truncated.mkdir()
                    seal_truncated = peer_truncated / ".encrypted-azure-auth.bin"
                    seal_truncated.write_bytes(b"HL")

                    # Open-failure case: the file exists when scanned, but opening it under the lock fails
                    # (peer logged out and re-sealed outside this sweep). An open failure is not proof of a
                    # legacy header, so the current seal must survive.
                    peer_recreated = shared_root / "peer_recreated"
                    peer_recreated.mkdir()
                    seal_recreated = peer_recreated / ".encrypted-azure-auth.bin"
                    seal_recreated.write_bytes(original_seal_bytes)

                    real_open = Path.open
                    def mock_open(path_obj, *args, **kwargs):
                        resolved = path_obj.resolve()
                        if resolved == seal_transient.resolve():
                            raise OSError("SMB transient read failure")
                        if resolved == seal_recreated.resolve():
                            # Recreate the file with valid HLS2 seal using real_open
                            with real_open(seal_recreated, "wb") as f:
                                f.write(original_seal_bytes)
                            raise FileNotFoundError("Simulated concurrent peer logout")
                        return real_open(path_obj, *args, **kwargs)

                    with patch.object(Path, "open", mock_open):
                        stats = hosted.sweep_legacy_azure_auth_seals(shared_root)

                    self.assertEqual(stats["scanned"], 5)
                    self.assertEqual(stats["kept"], 0)
                    self.assertEqual(stats["deleted"], 2)
                    self.assertEqual(stats["errors"], 3)

                    # Peer seals with read errors survived intact
                    self.assertTrue(seal_transient.exists())
                    self.assertEqual(seal_transient.read_bytes(), original_seal_bytes)

                    # Recreated peer replacement seal was not deleted
                    self.assertTrue(seal_recreated.exists())
                    self.assertEqual(seal_recreated.read_bytes(), original_seal_bytes)

                    # Truncated seal was not deleted without complete 4-byte header
                    self.assertTrue(seal_truncated.exists())
                    self.assertEqual(seal_truncated.read_bytes(), b"HL")

                    # Verified legacy headers were deleted
                    self.assertFalse(seal_legacy.exists())
                    self.assertFalse(seal_corrupt.exists())

    def _seal_env(self, data_dir: Path, cli_dir: Path) -> dict:
        return {
            "HLS_DATA_DIR": str(data_dir),
            "AZURE_CONFIG_DIR": str(cli_dir),
            "HLS_GATEWAY_KEY": "gateway-secret-key-for-user",
            "HLS_SANDBOX_USER_TID": "33333333-3333-4333-8333-333333333333",
            "HLS_SANDBOX_USER_OID": "55555555-5555-4555-8555-555555555555",
        }

    @staticmethod
    def _write_cli(cli_dir: Path, refresh_tokens: dict, profile=None) -> None:
        cli_dir.mkdir(parents=True, exist_ok=True)
        (cli_dir / "azureProfile.json").write_text(json.dumps(profile if profile is not None else {
            "subscriptions": [{"id": "11111111-2222-3333-4444-555555555555", "tenantId": "33333333-3333-4333-8333-333333333333", "isDefault": True}]
        }))
        (cli_dir / "msal_token_cache.json").write_text(json.dumps({
            "AccessToken": {}, "IdToken": {}, "RefreshToken": refresh_tokens,
            "Account": {"acct-1": {"username": "user@example.com"}}, "AppMetadata": {},
        }))

    def test_incomplete_credentials_never_replace_seal_or_active_cache(self):
        import zlib
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        with tempfile.TemporaryDirectory() as root_str:
            root = Path(root_str)
            data_dir, cli_dir = root / "data", root / "cli"
            with patch.dict(os.environ, self._seal_env(data_dir, cli_dir)):
                self._write_cli(cli_dir, {"rt-1": {"secret": "good-refresh-secret"}})
                self.assertTrue(hosted.seal_azure_auth_cache())
                seal_file = data_dir / ".encrypted-azure-auth.bin"
                good_seal = seal_file.read_bytes()

                # Incomplete CLI state must not be sealed over the existing valid seal.
                for tokens, profile in [
                    ({}, None),
                    ({"rt-1": {"secret": ""}}, None),
                    ({"rt-1": {"credential_type": "RefreshToken"}}, None),
                    ({"rt-1": {"secret": "good-refresh-secret"}}, {"installationId": "x"}),
                    ({"rt-1": {"secret": "good-refresh-secret"}}, []),
                    ({"rt-1": {"secret": "good-refresh-secret"}}, {"subscriptions": ["11111111-2222-3333-4444-555555555555"]}),
                ]:
                    self._write_cli(cli_dir, tokens, profile)
                    self.assertFalse(hosted.seal_azure_auth_cache())
                    self.assertEqual(seal_file.read_bytes(), good_seal)
                (cli_dir / "msal_token_cache.json").write_text("{not json")
                self.assertFalse(hosted.seal_azure_auth_cache())
                self.assertEqual(seal_file.read_bytes(), good_seal)

                # An authenticated seal whose decrypted payload has no usable refresh token is rejected
                # and never overwrites the active CLI cache, even when azureProfile.json is missing.
                payload = {"version": 2, "azureProfile": {"subscriptions": []},
                           "msalTokenCache": {"AccessToken": {}, "IdToken": {}, "RefreshToken": {}, "Account": {}, "AppMetadata": {}}}
                nonce = os.urandom(12)
                ciphertext = AESGCM(hosted._derive_seal_keys()[0]).encrypt(
                    nonce, zlib.compress(json.dumps(payload).encode()), b"hls-azure-auth-v2")
                seal_file.write_bytes(b"HLS2" + nonce + ciphertext)
                self._write_cli(cli_dir, {"active": {"secret": "active-refresh-secret"}})
                (cli_dir / "azureProfile.json").unlink()
                active_cache = (cli_dir / "msal_token_cache.json").read_bytes()
                self.assertFalse(hosted.restore_azure_auth_cache())
                self.assertEqual((cli_dir / "msal_token_cache.json").read_bytes(), active_cache)
                self.assertFalse((cli_dir / "azureProfile.json").exists())
                self.assertFalse(seal_file.exists())

                # A complete seal still round-trips into an empty CLI directory.
                self._write_cli(cli_dir, {"rt-1": {"secret": "good-refresh-secret"}})
                self.assertTrue(hosted.seal_azure_auth_cache())
                for f in cli_dir.iterdir():
                    f.unlink()
                self.assertTrue(hosted.restore_azure_auth_cache())
                restored = json.loads((cli_dir / "msal_token_cache.json").read_text())
                self.assertEqual(restored["RefreshToken"]["rt-1"]["secret"], "good-refresh-secret")
                self.assertEqual([p.name for p in data_dir.iterdir()], [".encrypted-azure-auth.bin"])

    def test_seal_cleanup_never_deletes_concurrent_replacement(self):
        import threading

        with tempfile.TemporaryDirectory() as root_str:
            root = Path(root_str)
            source_cli, data_dir, restore_cli = root / "source-cli", root / "share" / "own", root / "restore-cli"
            data_dir.mkdir(parents=True)
            restore_cli.mkdir()
            with patch.dict(os.environ, self._seal_env(data_dir, restore_cli)):
                self._write_cli(source_cli, {"rt-1": {"secret": "replacement-refresh-secret"}})
                seal_file = data_dir / ".encrypted-azure-auth.bin"

                def reseal_while_reading(read_old_seal):
                    # A writer re-seals while cleanup holds the old seal's contents; cleanup must not
                    # then unlink the replacement.
                    results = []
                    writer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache(source_cli, data_dir)))
                    old = read_old_seal()
                    writer.start()
                    writer.join(0.5)
                    return old, writer, results

                # Sweeper: legacy header read, writer races to replace it.
                seal_file.write_bytes(b"HLS1" + os.urandom(40))
                real_open = Path.open
                race = {}
                def racing_open(path_obj, *args, **kwargs):
                    if path_obj == seal_file and not race:
                        handle, race["writer"], race["results"] = reseal_while_reading(lambda: real_open(path_obj, *args, **kwargs))
                        return handle
                    return real_open(path_obj, *args, **kwargs)
                with patch.object(Path, "open", racing_open):
                    stats = hosted.sweep_legacy_azure_auth_seals(data_dir.parent)
                race["writer"].join(15)
                self.assertEqual(race["results"], [True])
                self.assertEqual(stats["deleted"], 1)
                self.assertEqual(seal_file.read_bytes()[:4], b"HLS2")

                # Restore: invalid envelope read, writer races to replace it.
                seal_file.write_bytes(b"BAD0" + os.urandom(40))
                real_read_bytes = Path.read_bytes
                race.clear()
                def racing_read_bytes(path_obj, *args, **kwargs):
                    if path_obj == seal_file and not race:
                        old, race["writer"], race["results"] = reseal_while_reading(lambda: real_read_bytes(path_obj, *args, **kwargs))
                        return old
                    return real_read_bytes(path_obj, *args, **kwargs)
                with patch.object(Path, "read_bytes", racing_read_bytes):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                race["writer"].join(15)
                self.assertEqual(race["results"], [True])
                self.assertTrue(hosted.restore_azure_auth_cache())
                restored = json.loads((restore_cli / "msal_token_cache.json").read_text())
                self.assertEqual(restored["RefreshToken"]["rt-1"]["secret"], "replacement-refresh-secret")

                # A held lock is a busy seal, not a corrupt one: cleanup leaves it in place.
                seal_file.write_bytes(b"HLS1" + os.urandom(40))
                with hosted._seal_lock(seal_file):
                    with patch.object(hosted, "_SWEEP_LOCK_TIMEOUT_SECONDS", 0.1):
                        stats = hosted.sweep_legacy_azure_auth_seals(data_dir.parent)
                self.assertEqual((stats["deleted"], stats["errors"]), (0, 1))
                self.assertTrue(seal_file.exists())

    def test_startup_sweep_gives_up_when_peer_lock_cannot_be_created(self):
        # A peer directory that refuses the lock file must cost the startup sweep its short lock
        # timeout, not spin forever; the peer's seal stays in place.
        with tempfile.TemporaryDirectory() as root_str:
            shared_root = Path(root_str)
            seal_file = shared_root / "peer" / ".encrypted-azure-auth.bin"
            seal_file.parent.mkdir()
            seal_file.write_bytes(b"HLS1" + os.urandom(40))
            real_open = os.open
            lock_attempts = []

            def deny_lock(path, flags, *args, **kwargs):
                if str(path).endswith(".lock"):
                    lock_attempts.append(path)
                    if len(lock_attempts) > 200:
                        raise AssertionError("seal lock kept retrying after its deadline")
                    raise PermissionError(13, "Permission denied", str(path))
                return real_open(path, flags, *args, **kwargs)

            with patch.object(hosted.os, "open", deny_lock), \
                 patch.object(hosted, "_SWEEP_LOCK_TIMEOUT_SECONDS", 0.1):
                stats = hosted.sweep_legacy_azure_auth_seals(shared_root)
            self.assertLess(len(lock_attempts), 200)
            self.assertEqual((stats["scanned"], stats["deleted"], stats["errors"]), (1, 0, 1))
            self.assertTrue(seal_file.exists())

    def test_hotfix_tar_requires_matching_image_commit_and_never_runs_from_shared_dir(self):
        import io
        import tarfile
        from shared.hotfix import HotfixError, apply_hotfixes

        def make_tar(path: Path, files: dict[str, bytes]) -> None:
            with tarfile.open(path, "w") as tf:
                for name, data in files.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))

        commit = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_dir, shared_dir, dest = base / "data", base / "share", base / "dest"
            data_dir.mkdir()
            shared_dir.mkdir()
            dest.mkdir()
            make_tar(data_dir / "hotfix.tar", {"evil.py": b"owned = True\n"})
            with patch.dict(os.environ, {"HLS_IMAGE_COMMIT": commit, "HLS_SHARED_DATA_DIR": str(shared_dir)}):
                self.assertEqual(apply_hotfixes(data_dir, [("hotfix.tar", dest)], reapply_applied=True), [])
            self.assertFalse((dest / "evil.py").exists())
            self.assertTrue((data_dir / "hotfix.tar.rejected").is_file())
            make_tar(data_dir / "hotfix.tar", {".hls-hotfix-commit": commit.encode(), "patched.txt": b"ok"})
            with patch.dict(os.environ, {"HLS_IMAGE_COMMIT": commit, "HLS_SHARED_DATA_DIR": str(shared_dir)}):
                self.assertEqual(apply_hotfixes(data_dir, [("hotfix.tar", dest)], reapply_applied=False), [dest])
            self.assertEqual((dest / "patched.txt").read_bytes(), b"ok")
            self.assertFalse((data_dir / "hotfix.tar").exists())
            self.assertTrue((data_dir / "hotfix.tar.applied").is_file())
            (data_dir / "hotfix.tar").write_bytes(b"not a tar")
            with patch.dict(os.environ, {"HLS_IMAGE_COMMIT": commit, "HLS_SHARED_DATA_DIR": str(shared_dir)}):
                with self.assertRaises(HotfixError):
                    apply_hotfixes(data_dir, [("hotfix.tar", dest)], reapply_applied=False)
                with self.assertRaises(HotfixError):
                    apply_hotfixes(shared_dir / "peer", [("hotfix.tar", dest)], reapply_applied=False)

    def test_history_import_preserves_live_deployments_schedules_on_loop_and_excludes_peer_active_runs(self):
        try:
            from tests import helpers
        except ImportError:
            import helpers
        local_server = helpers.get_isolated_local_server()
        live_obj = {"instanceId": "live-1", "runtimeStatus": "Running", "customStatus": {"workspaceName": "med-live"}}
        saved_deployments = dict(local_server.deployments)
        saved_tasks = dict(local_server._addon_tasks)
        saved_loop = local_server._MAIN_LOOP
        try:
            local_server.deployments.clear()
            local_server._addon_tasks.clear()
            local_server.deployments["live-1"] = live_obj
            imported_records = [
                {"instanceId": "live-1", "runtimeStatus": "Completed", "customStatus": {"importedFrom": "peer-a"}},
                {"instanceId": "peer-running", "runtimeStatus": "Running", "customStatus": {"importedFrom": "peer-a"}},
            ]
            scheduled: list[tuple] = []

            class FakeLoop:
                def is_running(self):
                    return True

                def call_soon_threadsafe(self, fn, *args):
                    scheduled.append((fn, args))
                    fn(*args)

            local_server._MAIN_LOOP = FakeLoop()
            with patch.object(local_server, "import_target_history_from_shared_storage", return_value={"importedDeployments": 2, "reconstructedLedgers": 0}), \
                 patch.object(local_server, "db_list_deployments", return_value=imported_records):
                local_server._sync_authenticated_target_history("tid", "sub")

            # Mutation was handed to the event loop via call_soon_threadsafe, and the live object identity is untouched.
            self.assertEqual(len(scheduled), 1)
            self.assertIs(local_server.deployments["live-1"], live_obj)
            self.assertEqual(local_server.deployments["live-1"]["runtimeStatus"], "Running")
            # Peer's Running record is present as read-only history, but excluded from _active_hosted_runs().
            self.assertEqual(local_server.deployments["peer-running"]["customStatus"]["importedFrom"], "peer-a")
            self.assertEqual(local_server._active_hosted_runs(), 1)
        finally:
            local_server.deployments.clear()
            local_server.deployments.update(saved_deployments)
            local_server._addon_tasks.clear()
            local_server._addon_tasks.update(saved_tasks)
            local_server._MAIN_LOOP = saved_loop

    def test_continuation_reload_preserves_event_and_parallel_addon_tasks_settle_only_when_empty(self):
        import importlib
        try:
            from tests import helpers
        except ImportError:
            import helpers
        local_server = helpers.get_isolated_local_server()
        from activities import addons
        from shared.continuations import CONTINUATIONS

        async def scenario():
            saved_deployments = dict(local_server.deployments)
            saved_tasks = dict(local_server._addon_tasks)
            try:
                # P2-7: reloading activities.addons does not reset CONTINUATIONS
                ev = asyncio.Event()
                CONTINUATIONS["inst-pause"] = ev
                importlib.reload(addons)
                self.assertIs(CONTINUATIONS.get("inst-pause"), ev)

                # P2-8: a second add-on finishing while Databricks is still paused leaves runtimeStatus Running
                dep = {
                    "instanceId": "inst-pause",
                    "runtimeStatus": "Running",
                    "customStatus": {"status": "running", "currentPhase": "Add-on: Databricks", "addons": {"databricks": {"status": "paused"}, "rayfin": {"status": "running"}}},
                    "output": {"phases": [], "resources": {}},
                }
                local_server.deployments["inst-pause"] = dep
                local_server._addon_tasks.clear()
                dbx_gate = asyncio.Event()
                dbx_task = asyncio.create_task(dbx_gate.wait())
                rayfin_done = asyncio.Event()
                rayfin_task = asyncio.create_task(rayfin_done.wait())
                local_server._track_addon_task("inst-pause", dbx_task)
                local_server._track_addon_task("inst-pause", rayfin_task)
                self.assertEqual(local_server._active_hosted_runs(), 3)

                rayfin_done.set()
                await rayfin_task
                self.assertFalse(local_server._release_addon_task("inst-pause", rayfin_task))
                self.assertIn("inst-pause", local_server._addon_tasks)

                dbx_gate.set()
                await dbx_task
                self.assertTrue(local_server._release_addon_task("inst-pause", dbx_task))
                self.assertNotIn("inst-pause", local_server._addon_tasks)
            finally:
                CONTINUATIONS.pop("inst-pause", None)
                local_server.deployments.clear()
                local_server.deployments.update(saved_deployments)
                local_server._addon_tasks.clear()
                local_server._addon_tasks.update(saved_tasks)

        asyncio.run(scenario())

    def test_continuation_skips_use_latest_phase_outcome_across_chain(self):
        try:
            from tests import helpers
        except ImportError:
            import helpers
        local_server = helpers.get_isolated_local_server()
        saved_deployments = dict(local_server.deployments)
        try:
            local_server.deployments.clear()
            # Run 1: Phase 4 Ontology succeeded, Phase 2 failed.
            local_server.deployments["run-1"] = {
                "instanceId": "run-1",
                "customStatus": {},
                "output": {"phases": [
                    {"phase": "Phase 1: Base Azure Infrastructure", "status": "succeeded"},
                    {"phase": "Phase 2: Fabric RTI", "status": "failed"},
                    {"phase": "Phase 4: Ontology", "status": "succeeded"},
                ]},
            }
            # Run 2 (continued from run-1): Phase 2 now succeeded, but Phase 4 Ontology was re-run and failed.
            run_2 = {
                "instanceId": "run-2",
                "customStatus": {"continuedFrom": "run-1"},
                "output": {"phases": [
                    {"phase": "Phase 2: Fabric RTI", "status": "succeeded"},
                    {"phase": "Phase 4: Ontology", "status": "failed"},
                ]},
            }
            local_server.deployments["run-2"] = run_2
            req = local_server.DeployRequest(
                expected_tenant_id="11111111-1111-1111-1111-111111111111",
                expected_subscription_id="22222222-2222-2222-2222-222222222222",
                resource_group_name="rg-med-test",
                fabric_workspace_name="med-test",
                admin_security_group="sg-admins",
                skip_quality_measures=True,
            )
            with patch.object(local_server, "_cloud_state_sync", return_value={"workspace": {"exists": True}, "resourceGroup": {"exists": True}}), \
                 patch.object(local_server, "_live_resume_prerequisites", return_value={"workspaceExists": True, "resourceGroupExists": True}), \
                 patch.object(local_server, "_phase_live_prerequisites_ok", return_value=(True, "ok")), \
                 patch.object(local_server, "_phase_has_blocking_logs", return_value=False):
                applied = local_server._apply_success_skips_from_deployment(req, run_2, "Continue")
            self.assertTrue(applied)
            # Phase 2's latest outcome is succeeded -> reuse_fabric_rti; Phase 4's latest outcome is failed -> NOT skipped.
            self.assertTrue(req.reuse_fabric_rti)
            self.assertFalse(req.skip_ontology)
        finally:
            local_server.deployments.clear()
            local_server.deployments.update(saved_deployments)

    def test_database_path_is_isolated_outside_repository(self):
        """Verify that importing local_server uses a database outside the repo (R5-1)."""
        try:
            from tests import helpers
        except ImportError:
            import helpers
        helpers.get_isolated_local_server()
        helpers.assert_database_isolated()
        from shared import database as db
        repo_root = Path(__file__).resolve().parents[2]
        self.assertFalse(db.DB_PATH.resolve().is_relative_to(repo_root))
        if db.BACKUP_PATH is not None:
            self.assertFalse(db.BACKUP_PATH.resolve().is_relative_to(repo_root))


_SEAL_TID = "33333333-3333-4333-8333-333333333333"
_SEAL_OID = "55555555-5555-4555-8555-555555555555"
_SEAL_SECRET = "very-distinctive-refresh-secret-7f3a"


def _seal_env(data_dir: Path, cli_dir: Path) -> dict:
    return {"HLS_DATA_DIR": str(data_dir), "AZURE_CONFIG_DIR": str(cli_dir), "HLS_GATEWAY_KEY": "gateway-secret-key-for-user",
            "HLS_SANDBOX_USER_TID": _SEAL_TID, "HLS_SANDBOX_USER_OID": _SEAL_OID}


def _write_signed_in_cli(cli_dir: Path, secret: str = _SEAL_SECRET, subscriptions=None) -> None:
    cli_dir.mkdir(parents=True, exist_ok=True)
    subs = [{"id": "11111111-2222-3333-4444-555555555555", "tenantId": _SEAL_TID}] if subscriptions is None else subscriptions
    (cli_dir / "azureProfile.json").write_text(json.dumps({"subscriptions": subs}))
    (cli_dir / "msal_token_cache.json").write_text(json.dumps({
        "AccessToken": {}, "IdToken": {}, "RefreshToken": {"rt-1": {"secret": secret}},
        "Account": {"acct-1": {"username": "user@example.com"}}, "AppMetadata": {}}))


def _age(path: Path, seconds: float) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


class SealLockAndSignOutTests(unittest.TestCase):
    """Seal lock exclusivity on an SMB share mounted ``nobrl`` and sign-out finality."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.data, self.cli = self.root / "data", self.root / "cli"
        self.data.mkdir()
        _write_signed_in_cli(self.cli)
        environment = patch.dict(os.environ, _seal_env(self.data, self.cli))
        environment.start()
        self.addCleanup(environment.stop)
        self.seal = self.data / hosted._SEAL_FILENAME
        self.lock = self.data / (hosted._SEAL_FILENAME + ".lock")

    def _sign_out(self):
        # Same order as /api/auth/logout: active CLI caches first, then the seal.
        for f in self.cli.iterdir():
            f.unlink()
        hosted.clear_azure_auth_seal()

    def _pause_sealer_after_cli_read(self):
        """Patch Path.read_bytes so the thread named 'sealer' stops right after reading the MSAL cache."""
        read_done, resume = threading.Event(), threading.Event()
        real_read_bytes = Path.read_bytes

        def paused(path_obj, *args, **kwargs):
            data = real_read_bytes(path_obj, *args, **kwargs)
            if (path_obj.name == "msal_token_cache.json" and threading.current_thread().name == "sealer"
                    and not read_done.is_set()):
                read_done.set()
                resume.wait(10)
            return data

        return patch.object(Path, "read_bytes", paused), read_done, resume

    def test_sign_out_is_final_against_sealer_that_read_credentials_first(self):
        # P1-1: the auth-status check (worker thread) reads the CLI files, then sign-out runs.
        reader, read_done, resume = self._pause_sealer_after_cli_read()
        results = []
        with reader:
            sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
            sealer.start()
            self.assertTrue(read_done.wait(5))
            sign_out = threading.Thread(target=self._sign_out, name="sign-out")
            sign_out.start()
            sign_out.join(0.5)
            resume.set()
            sealer.join(15)
            sign_out.join(15)
        self.assertFalse(sealer.is_alive() or sign_out.is_alive())
        self.assertFalse(self.seal.exists(), "a sealer that read credentials before sign-out re-created the seal")
        self.assertFalse(self.lock.exists())
        # Restart: nothing is restored, so the user stays signed out.
        self.assertFalse(hosted.restore_azure_auth_cache())
        self.assertEqual(list(self.cli.iterdir()), [])

    def test_sign_out_is_final_when_it_cannot_take_a_wedged_lock(self):
        # Sign-out that times out on the lock still wins over a sealer that read credentials before it.
        reader, read_done, resume = self._pause_sealer_after_cli_read()
        results = []
        replaced = []
        real_replace = os.replace

        def recording_replace(src, dst, *args, **kwargs):
            replaced.append(Path(dst))
            return real_replace(src, dst, *args, **kwargs)

        with reader, patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.3), patch.object(hosted.os, "replace", recording_replace):
            sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
            sealer.start()
            self.assertTrue(read_done.wait(5))
            self._sign_out()  # lock held by the paused sealer: times out, then clears anyway
            self.assertFalse(self.seal.exists())
            resume.set()
            sealer.join(15)
        self.assertEqual(results, [False])
        self.assertFalse(self.seal.exists(), "seal written after sign-out returned")
        # Credentials read before sign-out never reach the share, even briefly (a crash then would keep them).
        self.assertNotIn(self.seal, replaced)

    def test_sign_out_is_final_against_seal_write_stuck_in_io(self):
        # A seal write still in flight when sign-out gives up waiting for it makes sign-out report failure; the
        # seal is already gone, and the write removes its own file once it lands.
        writing, resume = threading.Event(), threading.Event()
        real_replace = hosted._replace_private

        def slow_replace(files):
            writing.set()
            resume.wait(10)
            return real_replace(files)

        results = []
        with patch.object(hosted, "_replace_private", slow_replace), patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.3):
            sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
            sealer.start()
            self.assertTrue(writing.wait(5))
            with self.assertRaises(hosted.SealWriteInProgress):
                self._sign_out()
            resume.set()
            sealer.join(15)
        self.assertEqual(results, [False])
        self.assertFalse(self.seal.exists(), "seal write that landed after sign-out was kept")

    def test_sign_out_removes_seal_write_that_landed_then_failed(self):
        # The seal rename lands, then the write reports an error (e.g. an SMB flush failure) after sign-out ran.
        writing, resume = threading.Event(), threading.Event()
        real_replace = hosted._replace_private

        def landed_then_failed(files):
            writing.set()
            resume.wait(10)
            real_replace(files)
            raise OSError(errno.EIO, "I/O error after rename")

        results = []
        with patch.object(hosted, "_replace_private", landed_then_failed), patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.3):
            sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
            sealer.start()
            self.assertTrue(writing.wait(5))
            with self.assertRaises(hosted.SealWriteInProgress):
                self._sign_out()
            resume.set()
            sealer.join(15)
        self.assertEqual(results, [False])
        self.assertFalse(self.seal.exists(), "seal that landed before its write failed was kept after sign-out")

    def _observe_sealer_polling(self):
        """Patch lock creation so ``polling`` is set once the thread named 'sealer' finds the lock busy."""
        polling = threading.Event()
        real_create = hosted._exclusive_create

        def observed_create(path, token):
            created = real_create(path, token)
            if not created and threading.current_thread().name == "sealer":
                polling.set()
            return created

        return patch.object(hosted, "_exclusive_create", observed_create), polling

    def test_sealer_queued_behind_peer_lock_seals_nothing_after_sign_out(self):
        # The review's sequence: a peer sweep holds our lock, the sealer polls, sign-out runs, the peer releases.
        self.assertTrue(hosted.seal_azure_auth_cache())
        self.lock.write_bytes(b"0" * 32)
        observer, polling = self._observe_sealer_polling()
        results = []
        with observer:
            sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
            sealer.start()
            self.assertTrue(polling.wait(5))
            for f in self.cli.iterdir():
                f.unlink()
            self.lock.unlink()
            hosted.clear_azure_auth_seal()
            sealer.join(15)
        self.assertEqual(results, [False])
        self.assertFalse(self.seal.exists())

    def test_sealer_queued_behind_peer_lock_seals_the_cli_state_current_when_it_gets_the_lock(self):
        # The CLI state changes (e.g. `az account set`) while a sealer waits on a peer's lock: the seal must hold
        # the new state, not what was on disk before the wait.
        self.lock.write_bytes(b"0" * 32)  # fresh peer lock
        observer, polling = self._observe_sealer_polling()
        results = []
        with observer:
            sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
            sealer.start()
            self.assertTrue(polling.wait(5))
            new_subs = [{"id": "99999999-8888-7777-6666-555555555555", "tenantId": _SEAL_TID}]
            _write_signed_in_cli(self.cli, "rotated-refresh-secret", subscriptions=new_subs)
            self.lock.unlink()  # peer releases
            sealer.join(15)
        self.assertEqual(results, [True])
        for f in self.cli.iterdir():
            f.unlink()
        self.assertTrue(hosted.restore_azure_auth_cache())
        self.assertEqual(json.loads((self.cli / "azureProfile.json").read_text())["subscriptions"], new_subs)
        restored = json.loads((self.cli / "msal_token_cache.json").read_text())
        self.assertEqual(restored["RefreshToken"]["rt-1"]["secret"], "rotated-refresh-secret")

    def test_sealer_starting_mid_sign_out_finds_nothing_to_seal(self):
        # A status check that starts sealing at any point during sign-out must not leave a seal behind.
        real_clear = hosted.clear_azure_auth_seal
        results = []

        def clear_then_concurrent_sealer(*args, **kwargs):
            real_clear(*args, **kwargs)
            results.append(hosted.seal_azure_auth_cache())

        self.assertTrue(hosted.seal_azure_auth_cache())
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}), \
                patch.object(hosted, "clear_azure_auth_seal", clear_then_concurrent_sealer):
            hosted._clear_local_azure_credentials()
        self.assertEqual(results, [False])
        self.assertFalse(self.seal.exists(), "sign-out left a seal written from CLI files it had not removed yet")
        self.assertEqual(list(self.cli.iterdir()), [])

    def test_new_sign_in_after_sign_out_is_sealed(self):
        self._sign_out()
        _write_signed_in_cli(self.cli, "second-sign-in-secret")
        self.assertTrue(hosted.seal_azure_auth_cache())
        for f in self.cli.iterdir():
            f.unlink()
        self.assertTrue(hosted.restore_azure_auth_cache())
        restored = json.loads((self.cli / "msal_token_cache.json").read_text())
        self.assertEqual(restored["RefreshToken"]["rt-1"]["secret"], "second-sign-in-secret")

    def test_sign_in_without_subscriptions_is_complete(self):
        # `az login --allow-no-subscriptions` is a valid sign-in; deploy preflight reports the missing subscription.
        _write_signed_in_cli(self.cli, subscriptions=[])
        self.assertTrue(hosted.seal_azure_auth_cache())
        for f in self.cli.iterdir():
            f.unlink()
        self.assertTrue(hosted.restore_azure_auth_cache())
        self.assertEqual(json.loads((self.cli / "azureProfile.json").read_text()), {"subscriptions": []})

    def test_stale_lock_break_never_admits_two_holders(self):
        # P2-1: B has judged the lock stale and is about to remove it when A arrives and judges it stale too.
        self.lock.write_bytes(b"crashed-holder")
        _age(self.lock, 120)
        events, guard = [], threading.Lock()
        b_removing, a_entered, resume_b = threading.Event(), threading.Event(), threading.Event()
        real_unlink = Path.unlink

        def record(name):
            with guard:
                events.append(name)

        def slow_unlink(path_obj, missing_ok=False):
            if path_obj == self.lock and threading.current_thread().name == "B" and not b_removing.is_set():
                b_removing.set()
                resume_b.wait(10)
            return real_unlink(path_obj, missing_ok=missing_ok)

        def holder(name, entered=None):
            with hosted._seal_lock(self.seal):
                record(f"{name} enter")
                if entered:
                    entered.set()
                time.sleep(0.2)
                record(f"{name} exit")

        with patch.object(Path, "unlink", slow_unlink):
            b = threading.Thread(target=holder, args=("B",), name="B")
            b.start()
            self.assertTrue(b_removing.wait(5))
            a = threading.Thread(target=holder, args=("A", a_entered), name="A")
            a.start()
            a_entered.wait(0.5)
            resume_b.set()
            b.join(15)
            a.join(15)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertEqual(len(events), 4)
        for first in range(0, 4, 2):
            holder_name = events[first].split()[0]
            self.assertEqual(events[first:first + 2], [f"{holder_name} enter", f"{holder_name} exit"], events)
        self.assertFalse(self.lock.exists())

    def test_release_after_being_broken_keeps_successor_lock(self):
        # M07: a holder that outlived the stale limit is broken; its late release must not free the successor's lock.
        successor_in, successor_go = threading.Event(), threading.Event()

        def successor():
            with hosted._seal_lock(self.seal):
                successor_in.set()
                successor_go.wait(10)

        with hosted._seal_lock(self.seal):
            _age(self.lock, 120)
            t = threading.Thread(target=successor)
            t.start()
            self.assertTrue(successor_in.wait(5))
            successor_token = self.lock.read_bytes()
        self.assertEqual(self.lock.read_bytes() if self.lock.exists() else None, successor_token,
                         "release removed a lock it no longer owned")
        with patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.2):
            self.assertFalse(hosted.seal_azure_auth_cache(), "a third writer entered while the successor held the lock")
        successor_go.set()
        t.join(15)
        self.assertFalse(self.lock.exists())

    def test_abandoned_locks_are_broken(self):
        # M10: crashed holders (garbage token, empty file, abandoned break election) never wedge the seal.
        for content in (b"crashed-holder", b"", b"a" * 32):
            self.lock.write_bytes(content)
            _age(self.lock, 120)
            if content == b"a" * 32:
                election = self.lock.with_name(f"{self.lock.name}.break.{'a' * 32}")
                election.write_bytes(b"b" * 32)
                _age(election, 120)
            started = time.monotonic()
            self.assertTrue(hosted.seal_azure_auth_cache(), content)
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(sorted(p.name for p in self.data.iterdir()), [hosted._SEAL_FILENAME])

    def test_live_lock_is_waited_for_not_broken(self):
        self.lock.write_bytes(b"c" * 32)
        with patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.3):
            started = time.monotonic()
            self.assertFalse(hosted.seal_azure_auth_cache())
            self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(self.lock.read_bytes(), b"c" * 32)
        self.assertFalse(self.seal.exists())

    def test_delete_pending_lock_name_is_retried(self):
        # P2-2: Linux cifs reports SMB STATUS_DELETE_PENDING as ENOENT while the directory exists.
        real_open = os.open
        attempts = []

        def delete_pending(path, flags, *args, **kwargs):
            if str(path).endswith(".lock"):
                attempts.append(path)
                if len(attempts) <= 3:
                    raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(path))
            return real_open(path, flags, *args, **kwargs)

        with patch.object(hosted.os, "open", delete_pending):
            self.assertTrue(hosted.seal_azure_auth_cache())
        self.assertEqual(len(attempts), 4)
        self.assertTrue(self.seal.is_file())
        self.assertFalse(self.lock.exists())

    def test_missing_seal_directory_fails_fast(self):
        missing = self.root / "gone" / hosted._SEAL_FILENAME
        started = time.monotonic()
        with self.assertRaises(FileNotFoundError) as caught:
            with hosted._seal_lock(missing):
                self.fail("lock acquired in a missing directory")
        self.assertIn("directory is missing", str(caught.exception))
        hosted.clear_azure_auth_seal(self.root / "gone")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_lock_token_write_failure_leaves_no_lock(self):
        # P3-1: an ownerless lock file would block every seal operation for the stale limit.
        real_write = os.write
        failed = []

        def disk_full_once(fd, data):
            if not failed and len(data) == 32:
                failed.append(fd)
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_write(fd, data)

        with patch.object(hosted.os, "write", disk_full_once):
            self.assertFalse(hosted.seal_azure_auth_cache())
        self.assertEqual(len(failed), 1)
        self.assertFalse(self.lock.exists())
        with patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.5):
            self.assertTrue(hosted.seal_azure_auth_cache())

    def test_busy_lock_keeps_seal_on_restore_and_still_signs_out(self):
        self.assertTrue(hosted.seal_azure_auth_cache())
        sealed = self.seal.read_bytes()
        for f in self.cli.iterdir():
            f.unlink()
        self.lock.write_bytes(b"d" * 32)  # a peer's sweep holds the lock
        with patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.2):
            # M14: a busy lock is not a bad seal.
            self.assertFalse(hosted.restore_azure_auth_cache())
            self.assertEqual(self.seal.read_bytes(), sealed)
            self.assertEqual(list(self.cli.iterdir()), [])
            # M16: sign-out removes the user's own seal even when it cannot take the lock.
            hosted.clear_azure_auth_seal()
        self.assertFalse(self.seal.exists())
        self.assertEqual(self.lock.read_bytes(), b"d" * 32, "sign-out removed a lock it does not own")

    def test_startup_sweep_waits_two_seconds_per_busy_peer(self):
        # M20: one busy peer must not hold up startup for the full seal-lock timeout.
        shared = self.root / "shared"
        for peer in ("peer-a", "peer-b"):
            (shared / peer).mkdir(parents=True)
            (shared / peer / hosted._SEAL_FILENAME).write_bytes(b"HLS1" + os.urandom(40))
            (shared / peer / (hosted._SEAL_FILENAME + ".lock")).write_bytes(b"e" * 32)
        clock = [1000.0]

        def fake_sleep(seconds):
            clock[0] += seconds

        with patch.object(hosted.time, "monotonic", lambda: clock[0]), patch.object(hosted.time, "sleep", fake_sleep):
            stats = hosted.sweep_legacy_azure_auth_seals(shared)
        self.assertEqual((stats["scanned"], stats["deleted"], stats["errors"]), (2, 0, 2))
        self.assertGreaterEqual(clock[0] - 1000.0, 4.0)
        self.assertLess(clock[0] - 1000.0, 4.5)

    def test_seal_and_restored_files_are_owner_only(self):
        # M21
        previous = os.umask(0)
        self.addCleanup(os.umask, previous)
        self.assertTrue(hosted.seal_azure_auth_cache())
        for f in self.cli.iterdir():
            f.unlink()
        self.assertTrue(hosted.restore_azure_auth_cache())
        for path in [self.seal, *self.cli.iterdir()]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)

    def test_failed_restore_leaves_active_files_and_no_temp_files(self):
        # M22/M23: restore stages every file before swapping any, and removes staged files on failure.
        self.assertTrue(hosted.seal_azure_auth_cache())
        sealed = self.seal.read_bytes()
        (self.cli / "msal_token_cache.json").unlink()
        (self.cli / "azureProfile.json").write_text('{"subscriptions": [], "marker": "active"}')
        active_profile = (self.cli / "azureProfile.json").read_bytes()
        real_os_open, real_path_open = os.open, Path.open

        def disk_full(name, flags):
            if "msal_token_cache" in name and flags & os.O_WRONLY:
                raise OSError(errno.ENOSPC, "No space left on device", name)

        def os_open(path, flags, *args, **kwargs):
            disk_full(Path(path).name, flags)
            return real_os_open(path, flags, *args, **kwargs)

        def path_open(path_obj, mode="r", *args, **kwargs):
            disk_full(path_obj.name, os.O_WRONLY if any(c in mode for c in "wax+") else 0)
            return real_path_open(path_obj, mode, *args, **kwargs)

        with patch.object(hosted.os, "open", os_open), patch.object(Path, "open", path_open):
            self.assertFalse(hosted.restore_azure_auth_cache())
        self.assertEqual((self.cli / "azureProfile.json").read_bytes(), active_profile)
        self.assertEqual(sorted(p.name for p in self.cli.iterdir()), ["azureProfile.json"])
        self.assertEqual(self.seal.read_bytes(), sealed)
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), [hosted._SEAL_FILENAME])

    def test_token_contents_never_logged(self):
        # M25: every warning path that handles credentials logs names and error types only.
        hosted_log = logging.getLogger(hosted.__name__)
        records = []
        handler = logging.Handler(logging.DEBUG)
        handler.emit = records.append
        hosted_log.addHandler(handler)
        previous_level = hosted_log.level
        hosted_log.setLevel(logging.DEBUG)
        self.addCleanup(hosted_log.removeHandler, handler)
        self.addCleanup(hosted_log.setLevel, previous_level)

        cache = self.cli / "msal_token_cache.json"
        tokens = {"rt-1": {"secret": _SEAL_SECRET}, "rt-2": {"secret": ""}}
        cache.write_text(json.dumps({"RefreshToken": tokens, "Account": {}, "AppMetadata": {}}))
        self.assertFalse(hosted.seal_azure_auth_cache())  # incomplete cache
        _write_signed_in_cli(self.cli)
        with patch.object(hosted, "_replace_private", side_effect=OSError(errno.EIO, f"I/O error near {_SEAL_SECRET}")):
            self.assertFalse(hosted.seal_azure_auth_cache())  # write failure
        self.assertTrue(hosted.seal_azure_auth_cache())
        for f in self.cli.iterdir():
            f.unlink()
        with patch.object(hosted, "_replace_private", side_effect=OSError(errno.EIO, "I/O error")):
            self.assertFalse(hosted.restore_azure_auth_cache())  # restore write failure
        self.lock.write_bytes(b"f" * 32)
        with patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.1):
            self.assertFalse(hosted.restore_azure_auth_cache())  # busy lock
            hosted.clear_azure_auth_seal()  # sign-out without the lock
        self.lock.unlink()
        with patch.dict(os.environ, {"HLS_GATEWAY_KEY": "another-sandbox-key"}):
            _write_signed_in_cli(self.root / "peer-cli")
            self.assertTrue(hosted.seal_azure_auth_cache(cli_dir=self.root / "peer-cli"))
        self.assertFalse(hosted.restore_azure_auth_cache())  # foreign seal deleted
        self.assertGreaterEqual(len(records), 5)
        for record in records:
            text = record.getMessage() + (logging.Formatter().formatException(record.exc_info) if record.exc_info else "")
            self.assertNotIn(_SEAL_SECRET, text)


class SealEventLoopTests(unittest.IsolatedAsyncioTestCase):
    """P2-3: waiting on the seal lock must never stall the server's event loop."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.data, self.cli = self.root / "data", self.root / "cli"
        self.data.mkdir()
        _write_signed_in_cli(self.cli)
        environment = patch.dict(os.environ, {**_seal_env(self.data, self.cli), "HOME": str(self.root / "home")})
        environment.start()
        self.addCleanup(environment.stop)
        sessions = patch.dict(hosted._sessions, {}, clear=True)
        sessions.start()
        self.addCleanup(sessions.stop)
        self.seal = self.data / hosted._SEAL_FILENAME
        self.lock = self.data / (hosted._SEAL_FILENAME + ".lock")

    async def _max_loop_gap_while(self, coroutine):
        ticks = []

        async def ticker():
            while True:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.02)

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        try:
            result = await coroutine
            await asyncio.sleep(0.05)  # let the ticker record a tick after the call, so a stall shows as a gap
        finally:
            task.cancel()
        return result, max(b - a for a, b in zip(ticks, ticks[1:]))

    async def test_sign_in_seal_waits_off_the_event_loop(self):
        self.lock.write_bytes(b"1" * 32)  # a peer's sweep holds the lock for a moment
        asyncio.get_running_loop().call_later(0.3, self.lock.unlink)
        process = AsyncMock()
        process.stdout = asyncio.StreamReader()
        process.stdout.feed_data(b"To sign in, use https://microsoft.com/devicelogin and enter the code ABCD12345 to authenticate.")
        process.stdout.feed_eof()
        process.returncode = 0
        session = {"status": "pending", "ready": asyncio.Event()}
        req = hosted.DeviceLoginRequest(tenant_id=_SEAL_TID, subscription_id="11111111-2222-3333-4444-555555555555", tool="az")
        run = AsyncMock(side_effect=["", "", json.dumps({"tenantId": _SEAL_TID})])
        with patch.object(hosted, "_run", run), patch.object(asyncio, "create_subprocess_exec", AsyncMock(return_value=process)), \
             patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 3.0):
            _, gap = await self._max_loop_gap_while(hosted._device_login(session, req, lambda: None))
        self.assertEqual(session["status"], "succeeded")
        self.assertLess(gap, 0.25)
        self.assertTrue(self.seal.is_file(), "seal not written once the peer released the lock")

    async def test_sign_out_waits_off_the_event_loop(self):
        self.assertTrue(hosted.seal_azure_auth_cache())
        self.lock.write_bytes(b"2" * 32)
        app = FastAPI()
        hosted.install_hosted_routes(app, lambda: 0, lambda: None)
        logout = next(route.endpoint for route in app.routes if route.path == "/api/auth/logout")
        with patch.object(hosted, "_run", AsyncMock(return_value="")), patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 1.0):
            response, gap = await self._max_loop_gap_while(logout())
        self.assertEqual(response, {"status": "signed_out"})
        self.assertLess(gap, 0.25)
        self.assertFalse(self.seal.exists())
        self.assertEqual(list(self.cli.iterdir()), [])

    def _logout_route(self):
        app = FastAPI()
        hosted.install_hosted_routes(app, lambda: 0, lambda: None)
        return next(route.endpoint for route in app.routes if route.path == "/api/auth/logout")

    async def _start_stalled_seal_write(self):
        """Start an auth-status sealer whose seal write stalls in SMB I/O until ``resume`` is set."""
        writing, resume = threading.Event(), threading.Event()
        real_replace = hosted._replace_private

        def stalled_replace(files):
            writing.set()
            resume.wait(30)
            return real_replace(files)

        stall = patch.object(hosted, "_replace_private", stalled_replace)
        stall.start()
        self.addCleanup(stall.stop)
        results = []
        sealer = threading.Thread(target=lambda: results.append(hosted.seal_azure_auth_cache()), name="sealer")
        sealer.start()
        self.addCleanup(sealer.join, 15)
        self.addCleanup(resume.set)
        self.assertTrue(await asyncio.to_thread(writing.wait, 5))
        return sealer, results, resume

    async def test_sign_out_fails_while_an_earlier_seal_write_is_stalled_and_succeeds_on_retry(self):
        self.assertTrue(hosted.seal_azure_auth_cache())  # the user's existing seal
        logout = self._logout_route()
        sealer, results, resume = await self._start_stalled_seal_write()
        with patch.object(hosted, "_run", AsyncMock(return_value="")), patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 0.5):
            # The writer holds the seal lock and the write guard: sign-out waits for both, then gives up.
            response, gap = await self._max_loop_gap_while(logout())
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["retry-after"], "10")
            body = json.loads(response.body)
            self.assertNotIn("status", body)
            self.assertTrue(body["error"] and body["error_hint"])
            self.assertLess(gap, 0.25)
            self.assertTrue(sealer.is_alive(), "the seal write was no longer stalled when sign-out answered")
            self.assertFalse(self.seal.exists())
            self.assertEqual(list(self.cli.iterdir()), [])

            resume.set()  # the stalled write lands after sign-out answered
            await asyncio.to_thread(sealer.join, 15)
            self.assertEqual(results, [False])
            self.assertFalse(self.seal.exists(), "seal write that landed after the failed sign-out was kept")

            self.assertEqual(await logout(), {"status": "signed_out"})
        self.assertFalse(self.seal.exists())
        self.assertFalse(self.lock.exists())

    async def test_sign_out_that_breaks_a_stalled_writers_lock_waits_once_for_its_write(self):
        # A writer stalled past the 60 s lease loses the seal lock but still holds the write guard. Sign-out
        # takes the lock, waits for the guard once and reports failure; it never repeats the wait without the lock.
        logout = self._logout_route()
        sealer, results, resume = await self._start_stalled_seal_write()
        _age(self.lock, 120)
        with patch.object(hosted, "_run", AsyncMock(return_value="")), patch.object(hosted, "_SEAL_LOCK_TIMEOUT_SECONDS", 1.0):
            started = time.monotonic()
            response = await logout()
            elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 503)
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, 1.8, "sign-out waited for the write guard again")
        resume.set()
        await asyncio.to_thread(sealer.join, 15)
        self.assertEqual(results, [False])
        self.assertFalse(self.seal.exists())


if __name__ == "__main__":
    unittest.main()
