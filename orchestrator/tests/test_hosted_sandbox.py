"""Offline checks for the hosted sandbox trust boundary and device-code contract."""
import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
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

            target_tid = "8d038e6a-9b7d-4cb8-bbcf-e84dff156478"
            target_sub = "9bbee190-dc61-4c58-ab47-1275cb04018f"

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
                            "alert_email": "alerts@brakekat.com",
                            "payer_ops_email": "ops@brakekat.com",
                            "deploy_cardiology": True,
                            "cardiology_location": "eastus2",
                            "cardiology_prefix": "cardio1024",
                            "cardiology_app_users": ["joey@brakekat.com", "alerts@brakekat.com"],
                        },
                    },
                }
                peer_db.save_deployment("P1234567-20261025-163943", peer_dep)
                peer_db.backfill_form_history_from_deployments()
                self.assertEqual(peer_db.get_form_history("naming-prefix"), ["med-1024"])
                self.assertEqual(peer_db.get_form_history("cardiology-prefix"), ["cardio1024"])
                self.assertEqual(set(peer_db.get_form_history("cardiology-app-users")), {"joey@brakekat.com", "alerts@brakekat.com"})

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
            (cli_dir / "azureProfile.json").write_text(json.dumps({
                "subscriptions": [{"id": "0525a464-e087-4084-a24e-a90396a83c15", "tenantId": "c77e97fc-1859-4575-8c8b-53d74bc35a63", "isDefault": True}]
            }))
            (cli_dir / "msal_token_cache.json").write_text(json.dumps({
                "AccessToken": {"at-1": {"secret": "must-be-stripped"}},
                "IdToken": {"id-1": {"secret": "must-be-stripped"}},
                "RefreshToken": {"rt-1": {"secret": "refresh-secret-value"}},
                "Account": {"acct-1": {"username": "joey@jbatl.dev"}},
                "AppMetadata": {},
            }))
            env = {
                "HLS_DATA_DIR": data_dir_str,
                "AZURE_CONFIG_DIR": cli_dir_str,
                "HLS_GATEWAY_KEY": "gateway-secret-key-for-user",
                "HLS_SANDBOX_USER_TID": "c77e97fc-1859-4575-8c8b-53d74bc35a63",
                "HLS_SANDBOX_USER_OID": "700530be-27dd-4cd2-aa2b-1937e3b24db8",
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

                # Another sandbox that only knows (tid, oid) — or has a different gateway key — cannot decrypt
                for f in cli_dir.iterdir():
                    f.unlink()
                with patch.dict(os.environ, {"HLS_GATEWAY_KEY": "different-sandbox-gateway-key"}):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                    self.assertFalse((cli_dir / "msal_token_cache.json").exists())
                with patch.dict(os.environ, {"HLS_SANDBOX_USER_OID": "00000000-0000-0000-0000-000000000000"}):
                    self.assertFalse(hosted.restore_azure_auth_cache())
                    self.assertFalse((cli_dir / "msal_token_cache.json").exists())

                # Legacy tid:oid-only seal migrates once and is re-sealed under the gateway-key secret
                legacy_salt = hosted.hashlib.sha256(f"{env['HLS_SANDBOX_USER_TID']}:{env['HLS_SANDBOX_USER_OID']}".encode()).digest()
                legacy_key = hosted._hkdf(f"hls-seal-v2:{env['HLS_SANDBOX_USER_TID']}:{env['HLS_SANDBOX_USER_OID']}".encode(), legacy_salt, b"hls-sandbox-azure-auth-seal-v1")
                nonce = b"123456789012"
                legacy_payload = hosted.zlib.compress(json.dumps({
                    "azureProfile": {"subscriptions": []},
                    "msalTokenCache": {"RefreshToken": {"rt-legacy": {"secret": "migrated-secret"}}, "Account": {}, "AppMetadata": {}, "AccessToken": {}, "IdToken": {}},
                }).encode())
                seal_file.write_bytes(b"HLS1" + nonce + hosted.AESGCM(legacy_key).encrypt(nonce, legacy_payload, b"hls-azure-auth-v1"))
                self.assertTrue(hosted.restore_azure_auth_cache())
                self.assertEqual(json.loads((cli_dir / "msal_token_cache.json").read_text())["RefreshToken"]["rt-legacy"]["secret"], "migrated-secret")
                with self.assertRaises(Exception):
                    hosted.AESGCM(legacy_key).decrypt(seal_file.read_bytes()[4:16], seal_file.read_bytes()[16:], b"hls-azure-auth-v1")

                # Verify logout clears the seal
                hosted.clear_azure_auth_seal()
                self.assertFalse(seal_file.exists())

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
        import local_server
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
        import local_server
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
        import local_server
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
if __name__ == "__main__":
    unittest.main()
