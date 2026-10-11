"""Live credential probe: mints real tokens and makes one read-only call per service.

``/api/auth/context`` only reports cached login state. A cached login can still fail to mint a token
(expired refresh token, revoked session, Conditional Access), so this probe acquires a token for every
audience a deployment uses through Azure CLI and Az PowerShell, requires each token's ``tid`` claim to
equal the subscription's tenant, and calls ARM, Fabric and Graph once. Tokens never leave this module.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from shared.full_teardown import ARM, DATABRICKS, FABRIC, GRAPH

STORAGE = "https://storage.azure.com"
FABRIC_SKILL = "search-consumption-cli"
MIN_REMAINING_SECONDS = 300

_PWSH_TOKEN_CLAIMS = r"""
$ErrorActionPreference = 'Stop'
$t = (Get-AzAccessToken -ResourceUrl $env:PROBE_RESOURCE -TenantId $env:PROBE_TENANT -ErrorAction Stop).Token
if ($t -is [System.Security.SecureString]) {
    $b = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($t)
    try { $t = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}
$p = $t.Split('.')[1].Replace('-', '+').Replace('_', '/')
$p = $p.PadRight($p.Length + ((4 - $p.Length % 4) % 4), '=')
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p))
"""

Runner = Callable[..., subprocess.CompletedProcess]
Fetch = Callable[[str, str, dict], tuple[int, Any]]


def _claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def _fetch(method: str, url: str, headers: dict) -> tuple[int, Any]:
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def _validate_claims(claims: dict, tenant: str, now: float) -> tuple[bool, str]:
    remaining = int(float(claims.get("exp", 0)) - now)
    if claims.get("tid") != tenant:
        return False, f"token tenant {claims.get('tid')} is not the subscription tenant {tenant}"
    if remaining < MIN_REMAINING_SECONDS:
        return False, f"token expires in {remaining}s"
    return True, f"{claims.get('upn') or claims.get('unique_name') or claims.get('appid') or 'identity'}, expires in {remaining // 60} min"


class LiveCredentialProbe:
    def __init__(self, run: Runner = subprocess.run, fetch: Fetch = _fetch, clock: Callable[[], float] = time.time) -> None:
        self._run, self._fetch, self._clock = run, fetch, clock
        # Azure CLI and Az PowerShell each keep one token cache file. Concurrent processes race on it
        # (measured: a parallel `az account get-access-token` reported "User does not exist in MSAL token
        # cache" for a healthy login) and can damage the user's login, so each tool's calls are serialized.
        self._az_lock, self._pwsh_lock = threading.Lock(), threading.Lock()

    def _az(self, *args: str) -> subprocess.CompletedProcess:
        with self._az_lock:
            return self._run(["az", *args, "-o", "json"], capture_output=True, text=True, timeout=90,
                             shell=sys.platform == "win32")

    def _cli_token(self, subscription: str, resource: str) -> tuple[str | None, str]:
        proc = self._az("account", "get-access-token", "--subscription", subscription, "--resource", resource)
        if proc.returncode != 0:
            return None, (proc.stderr or "az failed").strip().splitlines()[-1][:300]
        return json.loads(proc.stdout)["accessToken"], ""

    def probe(self, subscription_id: str = "") -> dict:
        account = self._az("account", "show", *(["--subscription", subscription_id] if subscription_id else []))
        if account.returncode != 0:
            return self._result("", "", "", [_check("Azure CLI login", False, (account.stderr or "not logged in").strip()[:300])])
        info = json.loads(account.stdout)
        subscription, tenant, user = info["id"], info["tenantId"], (info.get("user") or {}).get("name", "")
        checks = [_check("Azure CLI login", True, f"{user} on {info.get('name')}")]

        def cli_audience(label: str, resource: str) -> tuple[dict, str | None]:
            token, error = self._cli_token(subscription, resource)
            if token is None:
                return _check(f"Azure CLI {label} token", False, error), None
            ok, detail = _validate_claims(_claims(token), tenant, self._clock())
            return _check(f"Azure CLI {label} token", ok, detail), token

        def pwsh_audience(label: str, resource: str) -> dict:
            env = {**os.environ, "PROBE_RESOURCE": resource, "PROBE_TENANT": tenant}
            with self._pwsh_lock:
                proc = self._run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", _PWSH_TOKEN_CLAIMS],
                                 capture_output=True, text=True, timeout=120, env=env)
            if proc.returncode != 0:
                lines = (proc.stderr or proc.stdout or "pwsh failed").strip().splitlines()
                return _check(f"Az PowerShell {label} token", False, lines[-1][:300] if lines else "pwsh failed")
            ok, detail = _validate_claims(json.loads(proc.stdout), tenant, self._clock())
            return _check(f"Az PowerShell {label} token", ok, detail)

        audiences = {"ARM": ARM, "Fabric": FABRIC, "Graph": GRAPH, "Storage": STORAGE, "Databricks": DATABRICKS}
        with ThreadPoolExecutor(max_workers=8) as pool:
            cli_futures = {label: pool.submit(cli_audience, label, resource) for label, resource in audiences.items()}
            pwsh_futures = [pool.submit(pwsh_audience, label, audiences[label]) for label in ("ARM", "Fabric")]
            tokens: dict[str, str | None] = {}
            for label, future in cli_futures.items():
                check, tokens[label] = future.result()
                checks.append(check)
            checks.extend(future.result() for future in pwsh_futures)

            def api(name: str, label: str, url: str, extra: dict, verify: Callable[[Any], str | None]) -> dict:
                if not tokens.get(label):
                    return _check(name, False, f"skipped: no {label} token")
                status, body = self._fetch("GET", url, {"Authorization": f"Bearer {tokens[label]}", **extra})
                problem = None if status == 200 else f"HTTP {status}"
                problem = problem or verify(body)
                return _check(name, problem is None, problem or "HTTP 200")

            api_futures = [
                pool.submit(api, "ARM subscription read", "ARM",
                            f"{ARM}/subscriptions/{subscription}?api-version=2022-12-01", {},
                            lambda b: None if b.get("state") == "Enabled" and b.get("tenantId") == tenant
                            else f"subscription state {b.get('state')} tenant {b.get('tenantId')}"),
                pool.submit(api, "Fabric workspace list", "Fabric", f"{FABRIC}/v1/workspaces",
                            {"x-ms-fabric-skill": FABRIC_SKILL}, lambda b: None if "value" in b else "no workspace list"),
                pool.submit(api, "Graph identity read", "Graph", f"{GRAPH}/v1.0/me?$select=id,userPrincipalName", {},
                            lambda b: None if b.get("id") else "no identity returned"),
            ]
            checks.extend(future.result() for future in api_futures)
        return self._result(subscription, tenant, user, checks)

    def _result(self, subscription: str, tenant: str, user: str, checks: list[dict]) -> dict:
        return {"ok": all(c["status"] == "pass" for c in checks), "checkedAt": datetime.now(timezone.utc).isoformat(),
                "subscriptionId": subscription, "tenantId": tenant, "user": user, "checks": checks}
