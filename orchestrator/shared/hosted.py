"""Gateway-only sandbox access and ephemeral, in-container Azure device sign-in."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import time
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HOSTED = os.environ.get("HLS_HOSTED") == "1"
_log = logging.getLogger(__name__)
_NOTICE = "Your Azure sign-in stays inside your private sandbox and is deleted when the sandbox is removed. The operator of this host can technically access a running sandbox."
_CA_PATTERN = re.compile(r"AADSTS(?:53003|530033|50097)|blocked by Conditional Access|device code flow is blocked", re.I)
_CA_HINT = "Your tenant blocks device-code sign-in through Conditional Access. Ask your tenant administrator to exclude this flow/app from the blocking policy, or run the deployer locally."
_sessions: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()
_last_activity = datetime.now(timezone.utc).isoformat()



def touch_hosted_activity() -> None:
    global _last_activity
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


class DeploymentTarget(BaseModel):
    tenant_id: uuid.UUID
    subscription_id: uuid.UUID


class DeviceLoginRequest(DeploymentTarget):
    tool: Literal["az", "azps"] = "az"

def _save_target(target: DeploymentTarget) -> dict:
    from .database import add_form_history
    value = {"tenant_id": str(target.tenant_id), "subscription_id": str(target.subscription_id)}
    add_form_history("deployment-auth-target", json.dumps(value, sort_keys=True))
    return value


def _saved_target() -> dict | None:
    from .database import get_form_history
    values = get_form_history("deployment-auth-target", limit=1)
    if not values:
        return None
    try:
        return DeploymentTarget.model_validate_json(values[0]).model_dump(mode="json")
    except ValueError:
        return None



_SEAL_FILENAME = ".encrypted-azure-auth.bin"


def _seal_path(data_dir: Path | None = None) -> Path | None:
    root = data_dir or (Path(os.environ["HLS_DATA_DIR"]) if os.environ.get("HLS_DATA_DIR") else None)
    return (root / _SEAL_FILENAME) if root else None


def _hkdf(material: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(material)


def _derive_seal_keys() -> list[bytes]:
    """Return ``[current, *legacy]`` AES keys for the auth seal.

    The current key is derived from the per-sandbox ``HLS_GATEWAY_KEY`` secret, which only lives in this
    container's environment, with ``tid:oid`` bound in as HKDF info. Every sandbox can reach the shared
    Azure Files root, so a key derived from ``tid:oid`` alone lets one user decrypt another's refresh token.
    The legacy keys exist only so ``restore_azure_auth_cache`` can migrate an older seal, then re-seal it.
    """
    tid = os.environ.get("HLS_SANDBOX_USER_TID", "").strip().lower()
    oid = os.environ.get("HLS_SANDBOX_USER_OID", "").strip().lower()
    gw_key = os.environ.get("HLS_GATEWAY_KEY", "").strip()
    if not tid or not oid or not gw_key:
        return []
    identity = f"{tid}:{oid}".encode("utf-8")
    salt = hashlib.sha256(identity).digest()
    current = _hkdf(gw_key.encode("utf-8"), salt, b"hls-sandbox-azure-auth-seal-v3:" + identity)
    legacy_info = b"hls-sandbox-azure-auth-seal-v1"
    legacy = [_hkdf(f"hls-seal-v2:{tid}:{oid}".encode("utf-8"), salt, legacy_info),
              _hkdf(gw_key.encode("utf-8"), salt, legacy_info)]
    return [current, *legacy]


def seal_azure_auth_cache(cli_dir: Path | None = None, data_dir: Path | None = None) -> bool:
    """Encrypt and persist the Azure CLI MSAL refresh token cache and profile to HLS_DATA_DIR."""
    keys = _derive_seal_keys()
    seal_file = _seal_path(data_dir)
    if not keys or not seal_file:
        return False
    key = keys[0]
    cfg_dir = cli_dir or Path(os.environ.get("AZURE_CONFIG_DIR") or (Path.home() / ".azure"))
    prof_path = cfg_dir / "azureProfile.json"
    msal_path = cfg_dir / "msal_token_cache.json"
    if not prof_path.is_file() or not msal_path.is_file():
        return False
    try:
        prof = json.loads(prof_path.read_bytes().decode("utf-8-sig"))
        msal = json.loads(msal_path.read_bytes().decode("utf-8-sig"))
        # Strip short-lived access/ID tokens so only refresh tokens and account metadata are sealed
        msal_compact = {
            "AccessToken": {},
            "IdToken": {},
            "RefreshToken": msal.get("RefreshToken", {}),
            "Account": msal.get("Account", {}),
            "AppMetadata": msal.get("AppMetadata", {}),
        }
        payload_obj: dict = {
            "version": 1,
            "sealedAt": datetime.now(timezone.utc).isoformat(),
            "azureProfile": prof,
            "msalTokenCache": msal_compact,
        }
        azps_path = cfg_dir / "azps-context.json"
        if azps_path.is_file():
            try:
                payload_obj["azpsContext"] = json.loads(azps_path.read_bytes().decode("utf-8-sig"))
            except Exception:
                pass
        plaintext = zlib.compress(json.dumps(payload_obj, sort_keys=True).encode("utf-8"))
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, b"hls-azure-auth-v1")
        seal_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = seal_file.with_suffix(".bin.tmp")
        tmp_file.write_bytes(b"HLS1" + nonce + ciphertext)
        tmp_file.chmod(0o600)
        os.replace(tmp_file, seal_file)
        return True
    except Exception:
        return False


def restore_azure_auth_cache(cli_dir: Path | None = None, data_dir: Path | None = None) -> bool:
    """Restore encrypted Azure CLI MSAL refresh token cache from HLS_DATA_DIR into ephemeral HOME."""
    keys = _derive_seal_keys()
    seal_file = _seal_path(data_dir)
    if not keys or not seal_file or not seal_file.is_file():
        return False
    cfg_dir = cli_dir or Path(os.environ.get("AZURE_CONFIG_DIR") or (Path.home() / ".azure"))
    if (cfg_dir / "msal_token_cache.json").is_file() and (cfg_dir / "azureProfile.json").is_file():
        return True
    try:
        blob = seal_file.read_bytes()
        if len(blob) < 32 or blob[:4] != b"HLS1":
            return False
        nonce, ciphertext = blob[4:16], blob[16:]
        plaintext = None
        used = -1
        for index, key in enumerate(keys):
            try:
                plaintext = zlib.decompress(AESGCM(key).decrypt(nonce, ciphertext, b"hls-azure-auth-v1"))
                used = index
                break
            except Exception:
                continue
        if plaintext is None:
            return False
        payload_obj = json.loads(plaintext.decode("utf-8"))
        prof = payload_obj.get("azureProfile")
        msal = payload_obj.get("msalTokenCache")
        if not isinstance(prof, dict) or not isinstance(msal, dict):
            return False
        cfg_dir.mkdir(parents=True, exist_ok=True)
        prof_file = cfg_dir / "azureProfile.json"
        msal_file = cfg_dir / "msal_token_cache.json"
        prof_file.write_text(json.dumps(prof), encoding="utf-8")
        msal_file.write_text(json.dumps(msal), encoding="utf-8")
        prof_file.chmod(0o600)
        msal_file.chmod(0o600)
        azps = payload_obj.get("azpsContext")
        if isinstance(azps, dict):
            azps_file = cfg_dir / "azps-context.json"
            azps_file.write_text(json.dumps(azps), encoding="utf-8")
            azps_file.chmod(0o600)
        if used > 0 and not seal_azure_auth_cache(cfg_dir, data_dir):
            # A seal under a legacy key must not outlive the migration: the shared root exposes it.
            seal_file.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def clear_azure_auth_seal(data_dir: Path | None = None) -> None:
    seal_file = _seal_path(data_dir)
    if seal_file:
        seal_file.unlink(missing_ok=True)
def _login_snapshot(session_id: str, session: dict) -> dict:
    return {"session_id": session_id, "tool": session["tool"], **session["target"],
            "user_code": session.get("user_code"), "verification_uri": session.get("verification_uri"),
            "expires_in": max(0, 900 - int(time.monotonic() - session["created"]))}


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


async def _device_login(session: dict, req: DeviceLoginRequest, invalidate, on_target_authenticated=None) -> None:
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
        seal_azure_auth_cache()
        if on_target_authenticated is not None:
            try:
                # Blocking SQLite/share I/O: keep it off the event loop.
                res = await asyncio.to_thread(on_target_authenticated, tenant, subscription)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                # History import is best-effort for sign-in, but never silent.
                _log.exception("Importing prior history for the signed-in target failed")
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


def install_hosted_routes(app, active_runs, invalidate, on_target_authenticated=None):
    app.add_middleware(GatewayGuard)
    @app.get("/api/hosted/activity")
    async def activity():
        global _last_activity
        active = active_runs()
        if active > 0:
            _last_activity = datetime.now(timezone.utc).isoformat()
        return {"active_runs": active, "last_activity": _last_activity}

    @app.get("/api/hosted/whoami")
    async def whoami(request: Request):
        return {"hosted": HOSTED, "email": request.headers.get("X-HLS-User-Email", "") if HOSTED else "",
                "oid": request.headers.get("X-HLS-User-Oid", "") if HOSTED else "",
                "tid": request.headers.get("X-HLS-User-Tid", "") if HOSTED else "", "notice": _NOTICE}
    @app.get("/api/auth/state")
    async def auth_state():
        pending = None
        for session_id, session in _sessions.items():
            if session["status"] == "pending":
                pending = _login_snapshot(session_id, session)
                if pending["expires_in"] == 0:
                    await shutdown_auth()
                    session.update(status="failed", **_error("Device code expired; start a new sign-in"))
                    pending = None
                break
        return {"target": _saved_target(), "pending": pending}

    @app.put("/api/auth/target")
    async def save_target(target: DeploymentTarget):
        value = target.model_dump(mode="json")
        saved = _saved_target()
        if active_runs() or any(s["status"] == "pending" for s in _sessions.values()):
            if saved == value:
                return saved
            raise HTTPException(409, "Deployment target cannot change during an active run or sign-in")
        return _save_target(target)


    @app.post("/api/auth/device-login")
    async def login(req: DeviceLoginRequest):
        if active_runs():
            raise HTTPException(409, "Azure credentials cannot change during an active run")
        if any(s["status"] == "pending" for s in _sessions.values()):
            raise HTTPException(409, "Finish the current device sign-in before starting another")
        # No device codes or credentials are persisted to the history volume.
        _sessions.clear()
        session_id = uuid.uuid4().hex
        session = {"status": "pending", "ready": asyncio.Event(), "created": time.monotonic(),
                   "tool": req.tool, "target": _save_target(req)}
        _sessions[session_id] = session
        task = asyncio.create_task(_device_login(session, req, invalidate, on_target_authenticated))
        session["task"] = task
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
        return _login_snapshot(session_id, session)

    @app.get("/api/auth/device-login/{session_id}")
    async def status(session_id: str):
        session = _sessions.get(session_id)
        if not session:
            raise HTTPException(404, "Sign-in session not found; start a new sign-in")
        return {key: value for key, value in session.items() if key in {"status", "account", "error", "error_hint"}}
    @app.post("/api/auth/device-login/{session_id}/cancel")
    async def cancel(session_id: str):
        if active_runs():
            raise HTTPException(409, "Cannot cancel sign-in during an active run")
        session = _sessions.get(session_id)
        if not session:
            raise HTTPException(404, "Sign-in session not found")
        if session["status"] == "succeeded":
            raise HTTPException(409, "Sign-in already completed; refresh sign-in status")
        task = session.get("task")
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        session.update(status="failed", **_error("Sign-in cancelled; request a new code"))
        return {"status": "cancelled"}


    @app.post("/api/auth/logout")
    async def logout():
        if active_runs():
            raise HTTPException(409, "Cannot sign out during an active run")
        await shutdown_auth()
        errors = []
        for args in [("az", "account", "clear"), ("pwsh", "-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; if (Get-AzContext) { Disconnect-AzAccount -Scope CurrentUser | Out-Null }; Clear-AzContext -Scope CurrentUser -Force")]:
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
        clear_azure_auth_seal()
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
