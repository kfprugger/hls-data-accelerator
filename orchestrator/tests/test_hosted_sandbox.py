"""Offline checks for the hosted sandbox trust boundary and device-code contract."""
import asyncio
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
        for path, method in [("/", "GET"), ("/api/hosted/whoami", "GET"), ("/api/health", "POST"), ("/api/deploy/a/logs/stream", "GET")]:
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


if __name__ == "__main__":
    unittest.main()
