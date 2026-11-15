"""Gateway-only sandbox access and ephemeral, in-container Azure device sign-in."""
import asyncio
import base64
import contextlib
import errno
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import threading
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
# Seal writers, restorers and cross-sandbox sweepers serialize on an O_EXCL lock file beside the seal.
# Azure Files is mounted with ``nobrl``, so fcntl/flock locks are not shared between sandboxes; exclusive
# create is atomic on SMB and on local filesystems. The lock file holds its owner's random token.
# Critical sections are a few KB of I/O, so a lock older than the stale limit belongs to a crashed holder.
# A lock instance is only ever unlinked by the single winner of an exclusive-create election file named
# after that instance (``<lock>.break.<instance>``), which the winner re-checks before unlinking. Breaking a
# stale lock and releasing one's own lock both go through that election, so no check-then-delete can remove
# a successor's lock. An election file abandoned by a crashed winner is itself broken the same way.
_SEAL_LOCK_STALE_SECONDS = 60.0
_SEAL_LOCK_TIMEOUT_SECONDS = 10.0
_SWEEP_LOCK_TIMEOUT_SECONDS = 2.0
_SEAL_LOCK_RELEASE_SECONDS = 2.0
_SEAL_LOCK_POLL_SECONDS = 0.05
_LOCK_TOKEN = re.compile(rb"[0-9a-f]{32}")
# Sign-out vs. this sandbox's own sealers (auth-status worker threads, device sign-in). Each sign-out bumps
# the generation and unlinks the seal, holding the guard when it can get it within the lock timeout. A sealer
# reads the CLI files under the seal lock, writes only while holding the guard and only if no sign-out
# happened since before it read them, and removes its own write if a sign-out ran while it was writing.
# A sign-out that cannot get the guard still bumps and unlinks, then raises SealWriteInProgress: it is not
# final until that write lands and removes itself, so the route reports failure and the user retries.
_seal_write_guard = threading.Lock()
_seal_generation_lock = threading.Lock()
_seal_clear_generation = 0


def _seal_path(data_dir: Path | None = None) -> Path | None:
    root = data_dir or (Path(os.environ["HLS_DATA_DIR"]) if os.environ.get("HLS_DATA_DIR") else None)
    return (root / _SEAL_FILENAME) if root else None


class SealWriteInProgress(RuntimeError):
    """Sign-out invalidated and unlinked the seal, but a seal write of this sandbox was still in flight after
    the guard wait. That write deletes its own file when it lands; until then sign-out is not final.

    Deliberately not an OSError, so it is never handled as a busy or missing seal lock.
    """


def _lock_instance(path: Path) -> tuple[str, float] | None:
    """Return ``(instance id, age in seconds)`` of the lock-style file at ``path``, or None when it is absent.

    Content is read before metadata: a stale age then always belongs to the instance whose content was read,
    because any later instance is younger. A file with no valid token (holder crashed before writing it) is
    identified by its inode and mtime.
    """
    try:
        content = path.read_bytes()
        st = path.stat()
    except FileNotFoundError:
        return None
    if _LOCK_TOKEN.fullmatch(content):
        instance = content.decode("ascii")
    else:
        instance = "x" + hashlib.sha256(content + f":{st.st_ino}:{st.st_mtime_ns}".encode()).hexdigest()[:31]
    return instance, time.time() - st.st_mtime


def _exclusive_create(path: Path, token: bytes) -> bool:
    """Create ``path`` holding ``token``. Returns False when it exists or is still being deleted.

    Linux cifs reports an SMB delete-pending name as ENOENT, so ENOENT with the directory present is "busy".
    A missing directory raises FileNotFoundError. A failed token write removes the file before raising.
    """
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except (FileExistsError, PermissionError):
        return False  # PermissionError: SMB sharing/delete-pending denial; a truly unwritable directory times out.
    except FileNotFoundError as exc:
        if not path.parent.is_dir():
            raise FileNotFoundError(errno.ENOENT, "Azure auth seal directory is missing", str(path.parent)) from exc
        return False
    try:
        try:
            os.write(fd, token)
        finally:
            os.close(fd)
    except BaseException:
        path.unlink(missing_ok=True)  # Never leave an ownerless lock that would wedge the directory.
        raise
    return True


def _remove_lock_instance(path: Path, instance: str, token: bytes, deadline: float) -> bool:
    """Unlink ``path`` only while it is still ``instance``. True once that instance is gone; False on timeout.

    Only the winner of the exclusive-create election file for ``instance`` may unlink it. The instance's
    owner (if alive) and every other remover lose that election, so the re-check below cannot go stale
    before the unlink.
    """
    election = path.with_name(f"{path.name}.break.{instance}")
    while not _exclusive_create(election, token):
        try:
            holder = _lock_instance(election)
        except OSError:
            holder = None
        if holder is not None and holder[1] > _SEAL_LOCK_STALE_SECONDS:
            _log.warning("Breaking abandoned Azure auth seal lock election at %s", election)
            _remove_lock_instance(election, holder[0], token, deadline)
        elif time.monotonic() < deadline:
            time.sleep(_SEAL_LOCK_POLL_SECONDS)
        if time.monotonic() >= deadline:
            return False
    try:
        current = _lock_instance(path)
        if current is not None and current[0] == instance:
            path.unlink(missing_ok=True)
        return True
    finally:
        election.unlink(missing_ok=True)


@contextlib.contextmanager
def _seal_lock(seal_file: Path, timeout: float | None = None):
    """Hold the per-directory seal lock. Raises TimeoutError (an OSError) when it cannot be acquired.

    Raises FileNotFoundError at once when the seal directory does not exist. Not re-entrant: callers take
    it once and do all seal-file reads, replaces and unlinks inside. Blocking: never call on the event loop.
    """
    lock = seal_file.with_name(seal_file.name + ".lock")
    token = uuid.uuid4().hex.encode("ascii")
    deadline = time.monotonic() + (_SEAL_LOCK_TIMEOUT_SECONDS if timeout is None else timeout)
    while not _exclusive_create(lock, token):
        try:
            current = _lock_instance(lock)
        except OSError:
            current = None  # Unreadable right now (SMB sharing violation): treat as busy.
        if current is not None and current[1] > _SEAL_LOCK_STALE_SECONDS:
            _log.warning("Breaking stale Azure auth seal lock at %s", lock)
            _remove_lock_instance(lock, current[0], token, deadline)
        elif time.monotonic() < deadline:
            time.sleep(_SEAL_LOCK_POLL_SECONDS)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Azure auth seal lock busy at {lock}")
    try:
        yield
    finally:
        try:
            # Only our own instance is removed: if we outlived the stale limit and were broken, a successor's
            # lock carries a different token and stays.
            if not _remove_lock_instance(lock, token.decode("ascii"), token, time.monotonic() + _SEAL_LOCK_RELEASE_SECONDS):
                _log.warning("Azure auth seal lock at %s not released: its break election stayed busy", lock)
        except OSError as exc:
            _log.warning("Failed to release Azure auth seal lock at %s: %s", lock, type(exc).__name__)


def _valid_auth_payload(prof, msal) -> bool:
    """Return True when the profile and MSAL cache can actually restore an Azure CLI sign-in.

    Requires the Azure CLI shapes: ``azureProfile.json`` with a ``subscriptions`` list and an MSAL cache
    whose ``RefreshToken`` section is non-empty and holds only entries with a non-empty ``secret``.
    """
    if not isinstance(prof, dict) or not isinstance(prof.get("subscriptions"), list):
        return False
    if not all(isinstance(sub, dict) for sub in prof["subscriptions"]):
        return False
    if not isinstance(msal, dict) or not all(isinstance(msal.get(k, {}), dict) for k in ("Account", "AppMetadata")):
        return False
    tokens = msal.get("RefreshToken")
    return isinstance(tokens, dict) and bool(tokens) and all(
        isinstance(entry, dict) and isinstance(entry.get("secret"), str) and entry["secret"].strip()
        for entry in tokens.values()
    )


def _stage_private(path: Path, data: bytes) -> Path:
    """Write ``data`` to an owner-only temporary sibling of ``path``; the caller os.replace()s it."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _replace_private(files: dict[Path, bytes]) -> None:
    """Stage every file first, then replace, so a failed write never leaves a half-updated set."""
    staged: list[tuple[Path, Path]] = []
    try:
        for path, data in files.items():
            staged.append((_stage_private(path, data), path))
        for tmp, path in staged:
            os.replace(tmp, path)
    finally:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)


def _hkdf(material: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(material)


def _derive_seal_keys() -> list[bytes]:
    """Return ``[current]`` AES key for the auth seal.

    The key is derived from the per-sandbox ``HLS_GATEWAY_KEY`` secret, which only lives in this
    container's environment, with ``tid:oid`` bound in as HKDF info. Every sandbox can reach the shared
    Azure Files root, so a key derived from ``tid:oid`` alone lets one user decrypt another's refresh token.
    """
    tid = os.environ.get("HLS_SANDBOX_USER_TID", "").strip().lower()
    oid = os.environ.get("HLS_SANDBOX_USER_OID", "").strip().lower()
    gw_key = os.environ.get("HLS_GATEWAY_KEY", "").strip()
    if not tid or not oid or not gw_key:
        return []
    identity = f"{tid}:{oid}".encode("utf-8")
    salt = hashlib.sha256(identity).digest()
    current = _hkdf(gw_key.encode("utf-8"), salt, b"hls-sandbox-azure-auth-seal-v3:" + identity)
    return [current]


def _sealed_blob(cfg_dir: Path, key: bytes) -> bytes | None:
    """Read, validate and encrypt the active CLI sign-in. None when it is absent or incomplete."""
    prof_path = cfg_dir / "azureProfile.json"
    msal_path = cfg_dir / "msal_token_cache.json"
    try:
        prof_raw, msal_raw = prof_path.read_bytes(), msal_path.read_bytes()
    except FileNotFoundError:
        return None  # Signed out (or never signed in) since the caller looked.
    prof = json.loads(prof_raw.decode("utf-8-sig"))
    msal = json.loads(msal_raw.decode("utf-8-sig"))
    if not _valid_auth_payload(prof, msal):
        _log.warning("Not sealing Azure CLI credentials from %s: profile or refresh-token cache is incomplete", cfg_dir)
        return None
    # Strip short-lived access/ID tokens so only refresh tokens and account metadata are sealed
    msal_compact = {
        "AccessToken": {},
        "IdToken": {},
        "RefreshToken": msal["RefreshToken"],
        "Account": msal.get("Account", {}),
        "AppMetadata": msal.get("AppMetadata", {}),
    }
    payload_obj: dict = {
        "version": 2,
        "sealedAt": datetime.now(timezone.utc).isoformat(),
        "azureProfile": prof,
        "msalTokenCache": msal_compact,
    }
    azps_path = cfg_dir / "azps-context.json"
    if azps_path.is_file():
        try:
            azps = json.loads(azps_path.read_bytes().decode("utf-8-sig"))
            if isinstance(azps, dict):
                payload_obj["azpsContext"] = azps
        except Exception as exc:
            _log.warning("Sealing without Az PowerShell context from %s: %s", azps_path, type(exc).__name__)
    plaintext = zlib.compress(json.dumps(payload_obj, sort_keys=True).encode("utf-8"))
    nonce = os.urandom(12)
    return b"HLS2" + nonce + AESGCM(key).encrypt(nonce, plaintext, b"hls-azure-auth-v2")


def _seal_generation() -> int:
    with _seal_generation_lock:
        return _seal_clear_generation


def seal_azure_auth_cache(cli_dir: Path | None = None, data_dir: Path | None = None) -> bool:
    """Encrypt and persist the Azure CLI MSAL refresh token cache and profile to HLS_DATA_DIR.

    Incomplete CLI state (no usable refresh token, malformed profile) never replaces an existing seal.
    The CLI files are read under the seal lock, and the seal is written only if no sign-out has cleared the
    seal since this call started, so a sign-out can never be undone by credentials read before it.
    Blocking: async callers must use ``asyncio.to_thread``.
    """
    keys = _derive_seal_keys()
    seal_file = _seal_path(data_dir)
    if not keys or not seal_file:
        return False
    cfg_dir = cli_dir or Path(os.environ.get("AZURE_CONFIG_DIR") or (Path.home() / ".azure"))
    if not (cfg_dir / "azureProfile.json").is_file() or not (cfg_dir / "msal_token_cache.json").is_file():
        return False  # Cheap pre-check only; the sealing decision is re-made under the lock.
    generation = _seal_generation()
    try:
        seal_file.parent.mkdir(parents=True, exist_ok=True)
        with _seal_lock(seal_file):
            blob = _sealed_blob(cfg_dir, keys[0])
            if blob is None:
                return False
            if not _seal_write_guard.acquire(timeout=_SEAL_LOCK_TIMEOUT_SECONDS):
                raise TimeoutError("Azure auth seal write guard busy")
            try:
                if _seal_generation() != generation:
                    _log.info("Not sealing Azure CLI credentials to %s: signed out after they were read", seal_file)
                    return False
                try:
                    _replace_private({seal_file: blob})
                finally:
                    # A sign-out that could not wait for this write unlinked first; remove whatever the write left,
                    # including a write that landed and then raised.
                    signed_out = _seal_generation() != generation
                    if signed_out:
                        seal_file.unlink(missing_ok=True)
                        _log.info("Removed Azure auth seal at %s: signed out while it was being written", seal_file)
                if signed_out:
                    return False
            finally:
                _seal_write_guard.release()
        return True
    except Exception as exc:
        _log.warning("Failed to seal Azure CLI credentials to %s: %s", seal_file, type(exc).__name__)
        return False


def restore_azure_auth_cache(cli_dir: Path | None = None, data_dir: Path | None = None) -> bool:
    """Restore encrypted Azure CLI MSAL refresh token cache from HLS_DATA_DIR into ephemeral HOME.

    Verified-bad seals (wrong envelope, foreign key, incomplete payload) are deleted under the seal lock.
    Read or lock failures preserve the seal. Active CLI files are only replaced by a complete payload.
    """
    seal_file = _seal_path(data_dir)
    if not seal_file or not seal_file.is_file():
        return False
    keys = _derive_seal_keys()
    if not keys:
        # Do not delete when keys are unavailable (missing env) - that is a configuration problem, not a stale seal.
        _log.warning("Azure auth seal exists at %s but seal derivation keys are unavailable in environment", seal_file)
        return False
    cfg_dir = cli_dir or Path(os.environ.get("AZURE_CONFIG_DIR") or (Path.home() / ".azure"))
    if (cfg_dir / "msal_token_cache.json").is_file() and (cfg_dir / "azureProfile.json").is_file():
        return True

    def _delete_and_fail(reason: str) -> bool:
        # Caller holds the seal lock, so no writer can have replaced the seal that was just verified bad.
        _log.warning("Removing invalid Azure auth seal at %s: %s", seal_file, reason)
        try:
            seal_file.unlink(missing_ok=True)
        except Exception as exc:
            _log.warning("Failed to unlink invalid Azure auth seal at %s: %s", seal_file, exc)
        return False

    try:
        with _seal_lock(seal_file):
            try:
                blob = seal_file.read_bytes()
            except FileNotFoundError:
                return False
            except Exception as exc:
                _log.warning("Failed to read Azure auth seal at %s: %s", seal_file, exc)
                return False

            if len(blob) < 32 or blob[:4] != b"HLS2":
                return _delete_and_fail("unsupported seal version or corrupt envelope")

            nonce, ciphertext = blob[4:16], blob[16:]
            plaintext = None
            for key in keys:
                try:
                    plaintext = zlib.decompress(AESGCM(key).decrypt(nonce, ciphertext, b"hls-azure-auth-v2"))
                    break
                except Exception:
                    continue
            if plaintext is None:
                return _delete_and_fail("decryption failed under available keys")

            try:
                payload_obj = json.loads(plaintext.decode("utf-8"))
            except Exception as exc:
                return _delete_and_fail(f"payload JSON decode failed: {type(exc).__name__}")

            if not isinstance(payload_obj, dict) or payload_obj.get("version") != 2:
                return _delete_and_fail(f"unsupported payload version ({payload_obj.get('version') if isinstance(payload_obj, dict) else 'non-dict'})")

            prof = payload_obj.get("azureProfile")
            msal = payload_obj.get("msalTokenCache")
            if not _valid_auth_payload(prof, msal):
                return _delete_and_fail("payload profile or refresh-token cache is incomplete")

            files = {
                cfg_dir / "azureProfile.json": json.dumps(prof).encode("utf-8"),
                cfg_dir / "msal_token_cache.json": json.dumps(msal).encode("utf-8"),
            }
            azps = payload_obj.get("azpsContext")
            if isinstance(azps, dict):
                files[cfg_dir / "azps-context.json"] = json.dumps(azps).encode("utf-8")
            try:
                cfg_dir.mkdir(parents=True, exist_ok=True)
                _replace_private(files)
            except Exception as exc:
                _log.warning("Failed to write restored credentials to %s: %s", cfg_dir, exc)
                return False
            return True
    except OSError as exc:
        _log.warning("Azure auth seal at %s left in place; lock unavailable: %s", seal_file, exc)
        return False

def _unlink_seal_for_sign_out(seal_file: Path) -> None:
    """Invalidate in-flight sealers of this sandbox, then delete the seal, serialized with their writes.

    Raises SealWriteInProgress after invalidating and unlinking when a write still held the guard at timeout.
    """
    global _seal_clear_generation
    guarded = _seal_write_guard.acquire(timeout=_SEAL_LOCK_TIMEOUT_SECONDS)
    try:
        with _seal_generation_lock:
            _seal_clear_generation += 1
        seal_file.unlink(missing_ok=True)
    finally:
        if guarded:
            _seal_write_guard.release()
    if not guarded:
        # The writer re-checks the generation after its write lands and removes its seal; this sign-out cannot
        # report success before that.
        _log.warning("Azure auth seal at %s cleared while a seal write is still in progress", seal_file)
        raise SealWriteInProgress(f"Azure auth seal write at {seal_file} is still in progress")


def clear_azure_auth_seal(data_dir: Path | None = None) -> None:
    """Sign-out: delete this sandbox's seal so no sealer can re-create it from earlier credentials.

    Callers remove the active CLI files first. At most two bounded waits run in sequence: the seal lock, then
    the write guard. Raises SealWriteInProgress when a seal write is still in flight after the guard wait; the
    caller must not report sign-out as done. Blocking: async callers must use ``asyncio.to_thread``.
    """
    seal_file = _seal_path(data_dir)
    if not seal_file:
        return
    with contextlib.ExitStack() as held:
        try:
            held.enter_context(_seal_lock(seal_file))
        except FileNotFoundError:
            pass  # data directory itself is gone: nothing on disk to clear, but in-flight sealers still must stop
        except OSError as exc:
            # Sign-out must still remove the user's own seal even when the lock is wedged.
            _log.warning("Clearing Azure auth seal at %s without its lock: %s", seal_file, type(exc).__name__)
        # Outside the lock-acquisition handlers: a guard timeout or unlink failure here is never retried.
        _unlink_seal_for_sign_out(seal_file)

def _sweep_seal_locked(seal_file: Path) -> str:
    """Classify and maybe delete one seal; caller holds its lock. Returns the stats key to count."""
    try:
        with seal_file.open("rb") as f:
            header = f.read(4)
    except Exception as read_exc:
        _log.warning("Cannot read seal header at %s: %s", seal_file, read_exc)
        return "errors"
    if len(header) < 4:
        _log.warning("Incomplete seal header at %s: read %d bytes, expected 4", seal_file, len(header))
        return "errors"
    if header == b"HLS2":
        return "kept"
    try:
        seal_file.unlink(missing_ok=True)
    except Exception as del_exc:
        _log.warning("Failed to delete legacy Azure auth seal at %s: %s", seal_file, del_exc)
        return "errors"
    _log.info("Deleted legacy Azure auth seal at %s (header=%r)", seal_file, header)
    return "deleted"


def sweep_legacy_azure_auth_seals(shared_root: Path | None = None) -> dict[str, int]:
    """Startup sweep: delete legacy (version != 2) seals across all sandbox directories.

    Scans only one level deep (<root>/*/<seal file name>). Never recurse further.
    Never reads contents beyond the 4-byte version header.
    Header check and unlink happen under the peer's seal lock so a concurrent re-seal is never deleted;
    a busy lock or unreadable header leaves the seal in place.
    Never raises out of startup.
    """
    stats = {"scanned": 0, "kept": 0, "deleted": 0, "errors": 0}
    try:
        root_path = shared_root or (Path(os.environ["HLS_SHARED_DATA_DIR"]) if os.environ.get("HLS_SHARED_DATA_DIR") else None)
        if not root_path or not root_path.is_dir():
            return stats
        for child in root_path.iterdir():
            try:
                if not child.is_dir():
                    continue
                seal_file = child / _SEAL_FILENAME
                if not seal_file.is_file():
                    continue
                stats["scanned"] += 1
                try:
                    with _seal_lock(seal_file, _SWEEP_LOCK_TIMEOUT_SECONDS):
                        outcome = _sweep_seal_locked(seal_file)
                except OSError as lock_exc:
                    _log.warning("Skipping seal at %s; lock unavailable: %s", seal_file, lock_exc)
                    outcome = "errors"
                stats[outcome] += 1
            except Exception as child_exc:
                stats["errors"] += 1
                _log.warning("Error inspecting sandbox directory %s: %s", child, child_exc)
        _log.info(
            "Legacy auth seal sweep finished: scanned=%d, kept=%d, deleted=%d, errors=%d",
            stats["scanned"], stats["kept"], stats["deleted"], stats["errors"]
        )
    except Exception as exc:
        _log.warning("Legacy auth seal sweep encountered unexpected error: %s", exc)
        stats["errors"] += 1
    return stats
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
        # The seal lock can wait up to its timeout: keep it off the event loop.
        await asyncio.to_thread(seal_azure_auth_cache)
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


def _clear_local_azure_credentials() -> None:
    """Remove the active Azure CLI / Az PowerShell caches, then the seal; that order lets a concurrent sealer
    that reads after the seal is cleared find nothing to seal. Propagates SealWriteInProgress."""
    # Az.Accounts token caches are local to HOME, never the mounted history.
    shutil.rmtree(Path.home() / ".Azure", ignore_errors=False) if (Path.home() / ".Azure").exists() else None
    cli_dir = Path(os.environ.get("AZURE_CONFIG_DIR") or Path.home() / ".azure")
    for pattern in ("msal*", "azureProfile.json", "accessTokens.json", "azps-context.json"):
        for cache in cli_dir.glob(pattern):
            if cache.is_file():
                cache.unlink()
    clear_azure_auth_seal()


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
        # File I/O and the seal waits (two bounded waits at most) must not block the event loop.
        try:
            await asyncio.to_thread(_clear_local_azure_credentials)
            seal_write_pending = False
        except SealWriteInProgress:
            seal_write_pending = True
        _sessions.clear()
        invalidate()
        if seal_write_pending:
            # The CLI files and seal are gone, but an earlier sign-in save is still writing; it removes itself
            # when it lands. Sign-out is idempotent, so retrying is safe and reports success once that is done.
            return JSONResponse({"error": "; ".join(["Sign-out is not finished: a sign-in save that started before it is still writing", *errors]),
                                 "error_hint": "Wait 10 seconds, then sign out again. Do not treat this sandbox as signed out until sign-out succeeds."},
                                status_code=503, headers={"Retry-After": "10"})
        if errors:
            return JSONResponse({"error": "; ".join(errors)}, status_code=502)
        return {"status": "signed_out"}


async def shutdown_auth():
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
