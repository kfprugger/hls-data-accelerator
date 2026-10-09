"""Gateway-only sandbox access and ephemeral, in-container Azure device sign-in."""
import asyncio
import hmac
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HOSTED = os.environ.get("HLS_HOSTED") == "1"
_NOTICE = "Your Azure sign-in stays inside your private sandbox and is deleted when the sandbox is removed. The operator of this host can technically access a running sandbox."
_CA_PATTERN = re.compile(r"AADSTS(?:53003|530033|50097)|blocked by Conditional Access|device code flow is blocked", re.I)
_CA_HINT = "Your tenant blocks device-code sign-in through Conditional Access. Ask your tenant administrator to exclude this flow/app from the blocking policy, or run the deployer locally."
_sessions: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()
_last_activity = datetime.now(timezone.utc).isoformat()


class GatewayGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        global _last_activity
        if scope["type"] in {"http", "websocket"}:
            health = scope.get("method") == "GET" and scope["path"] == "/api/health"
            headers = dict(scope.get("headers", []))
            key = os.environ.get("HLS_GATEWAY_KEY", "").encode()
            if HOSTED and not health and (not key or not hmac.compare_digest(headers.get(b"x-hls-gateway-key", b""), key)):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse({"error": "Gateway authentication required"}, status_code=403)(scope, receive, send)
                return
            # Gateway sweeps and passive browser liveness polling must not defeat idle deletion.
            if scope["path"] not in {"/api/health", "/api/live", "/api/hosted/activity", "/api/hosted/whoami", "/api/auth/context"}:
                _last_activity = datetime.now(timezone.utc).isoformat()
        await self.app(scope, receive, send)


class DeviceLoginRequest(BaseModel):
    tenant_id: uuid.UUID
    subscription_id: uuid.UUID
    tool: Literal["az", "azps"]


def _error(output: str) -> dict:
    return {"error": output[-2000:] or "Azure sign-in failed", "error_hint": _CA_HINT if _CA_PATTERN.search(output) else "Check the tenant and subscription IDs, then start a new sign-in."}


async def _run(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 60)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    text = output.decode("utf-8", errors="replace")
    if process.returncode:
        raise RuntimeError(text)
    return text


async def _device_login(session: dict, req: DeviceLoginRequest, invalidate) -> None:
    process = None
    output = ""
    tenant, subscription = str(req.tenant_id), str(req.subscription_id)
    try:
        if req.tool == "az":
            await _run("az", "config", "set", "core.login_experience_v2=off")
            args = ["az", "login", "--use-device-code", "--tenant", tenant, "--allow-no-subscriptions", "--output", "none"]
        else:
            # UUID-only values prevent PowerShell interpolation/injection.
            command = ("$ErrorActionPreference='Stop'; $WarningPreference='Continue'; $PSStyle.OutputRendering='PlainText'; "
                       "Update-AzConfig -EnableLoginByWam $false -LoginExperienceV2 Off -Scope CurrentUser | Out-Null; "
                       "Enable-AzContextAutosave -Scope CurrentUser | Out-Null; "
                       f"Connect-AzAccount -UseDeviceAuthentication -Tenant '{tenant}' -Subscription '{subscription}' | Out-Null; "
                       f"Set-AzContext -Tenant '{tenant}' -Subscription '{subscription}' | Out-Null")
            args = ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command]
        process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        session["process"] = process
        async with asyncio.timeout(900):
            while chunk := await process.stdout.read(1024):
                output = (output + chunk.decode("utf-8", errors="replace"))[-16000:]
                plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
                code = re.search(r"\bcode\s+([A-Z0-9-]{6,20})\b", plain)
                uri = re.search(r"https://(?:www\.)?(?:microsoft\.com/devicelogin|login\.microsoft\.com/device|aka\.ms/devicelogin|login\.microsoftonline\.com/common/oauth2/deviceauth)", plain, re.I)
                if code and uri and not session.get("user_code"):
                    session.update(user_code=code.group(1), verification_uri=uri.group(0))
                    session["ready"].set()
            await process.wait()
        if process.returncode:
            raise RuntimeError(output)
        if req.tool == "az":
            await _run("az", "account", "set", "--subscription", subscription)
            account = json.loads(await _run("az", "account", "show", "--output", "json"))
            if account.get("tenantId", "").lower() != tenant:
                raise RuntimeError("Selected subscription is not in the requested tenant")
        else:
            account = {"tenantId": tenant, "subscriptionId": subscription}
        session.update(status="succeeded", account=account)
        invalidate()
    except asyncio.CancelledError:
        session.update(status="failed", **_error("Sign-in cancelled"))
        raise
    except Exception as exc:
        session.update(status="failed", **_error(str(exc) or "Device code expired; start a new sign-in"))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        session.pop("process", None)
        session["ready"].set()


def install_hosted_routes(app, active_runs, invalidate):
    app.add_middleware(GatewayGuard)

    @app.get("/api/hosted/activity")
    async def activity():
        return {"active_runs": active_runs(), "last_activity": _last_activity}

    @app.get("/api/hosted/whoami")
    async def whoami(request: Request):
        return {"hosted": HOSTED, "email": request.headers.get("X-HLS-User-Email", "") if HOSTED else "",
                "oid": request.headers.get("X-HLS-User-Oid", "") if HOSTED else "",
                "tid": request.headers.get("X-HLS-User-Tid", "") if HOSTED else "", "notice": _NOTICE}

    @app.post("/api/auth/device-login")
    async def login(req: DeviceLoginRequest):
        if active_runs():
            raise HTTPException(409, "Azure credentials cannot change during an active run")
        if any(s["status"] == "pending" for s in _sessions.values()):
            raise HTTPException(409, "Finish the current device sign-in before starting another")
        # No device codes or credentials are persisted to the history volume.
        _sessions.clear()
        session_id = uuid.uuid4().hex
        session = {"status": "pending", "ready": asyncio.Event(), "created": time.monotonic()}
        _sessions[session_id] = session
        task = asyncio.create_task(_device_login(session, req, invalidate))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        try:
            await asyncio.wait_for(session["ready"].wait(), 45)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return JSONResponse(_error("Azure did not issue a device code within 45 seconds"), status_code=502)
        if not session.get("user_code"):
            return JSONResponse({k: v for k, v in session.items() if k in {"error", "error_hint"}}, status_code=400)
        return {"session_id": session_id, "user_code": session["user_code"], "verification_uri": session["verification_uri"], "expires_in": max(0, 900 - int(time.monotonic() - session["created"]))}

    @app.get("/api/auth/device-login/{session_id}")
    async def status(session_id: str):
        session = _sessions.get(session_id)
        if not session:
            raise HTTPException(404, "Sign-in session not found; start a new sign-in")
        return {key: value for key, value in session.items() if key in {"status", "account", "error", "error_hint"}}

    @app.post("/api/auth/logout")
    async def logout():
        if active_runs():
            raise HTTPException(409, "Cannot sign out during an active run")
        await shutdown_auth()
        errors = []
        for args in [("az", "account", "clear"), ("pwsh", "-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; Clear-AzContext -Scope CurrentUser -Force; Disconnect-AzAccount -Scope CurrentUser -ErrorAction SilentlyContinue | Out-Null")]:
            try:
                await _run(*args)
            except Exception as exc:
                errors.append(str(exc))
        # Az.Accounts token caches are local to HOME, never the mounted history.
        shutil.rmtree(Path.home() / ".Azure", ignore_errors=False) if (Path.home() / ".Azure").exists() else None
        cli_dir = Path(os.environ.get("AZURE_CONFIG_DIR") or Path.home() / ".azure")
        for pattern in ("msal*", "azureProfile.json", "accessTokens.json", "azps-context.json"):
            for cache in cli_dir.glob(pattern):
                if cache.is_file():
                    cache.unlink()
        _sessions.clear()
        invalidate()
        if errors:
            return JSONResponse({"error": "; ".join(errors)}, status_code=502)
        return {"status": "signed_out"}


async def shutdown_auth():
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
