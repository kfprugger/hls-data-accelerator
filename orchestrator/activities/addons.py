"""Subscription-pinned add-ons over a completed HLS estate; no interactive login."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from shared.continuations import CONTINUATIONS
from shared.full_teardown import AzureCliTokens, ARM, FABRIC, GRAPH, DATABRICKS
from shared.hotfix import apply_hotfixes, default_targets
from shared.runtime_paths import DATA_DIR

ROOT = Path(__file__).resolve().parents[2]
ADDON_FLAGS = {"cardiology": "deploy_cardiology", "rayfin": "deploy_rayfin_apps", "databricks": "deploy_databricks"}
MODEL_CANDIDATES = [("gpt-5.6-luna", "2026-07-09"), ("gpt-5.5", "2026-04-24")]
CARDIOLOGY_FALLBACK_REGIONS = ("eastus2", "eastus", "westus", "westus3", "northcentralus", "southcentralus", "centralus", "swedencentral")
DATABRICKS_PROVIDERS = ("Microsoft.Databricks", "Microsoft.Storage", "Microsoft.EventHub", "Microsoft.KeyVault", "Microsoft.EventGrid")
CARDIOLOGY_PROVIDERS = ("Microsoft.App", "Microsoft.CognitiveServices", "Microsoft.OperationalInsights")
# The Rayfin CLI writes one diagnostic log per invocation under
# $RAYFIN_CONFIG_DIR/logs (default ~/.rayfin/logs), keeps only the newest 20,
# and the hosted sandbox home is wiped on image rollout. Copy each log out.
RAYFIN_LOG_LINE_LIMIT = 2000
RAYFIN_LOG_LEVELS = {"debug": "info", "info": "info", "warn": "warn", "warning": "warn", "error": "error"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def selected(config: dict) -> list[str]:
    return [name for name, flag in ADDON_FLAGS.items() if config.get(flag)]


def rayfin_log_dir(env: dict) -> Path:
    """Return the Rayfin CLI diagnostic log directory that ``env`` selects."""
    config_dir = env.get("RAYFIN_CONFIG_DIR") or str(Path(env.get("HOME") or Path.home()) / ".rayfin")
    return Path(config_dir) / "logs"


def rayfin_log_for_pid(log_dir: Path, pid: int) -> Path | None:
    """Find the diagnostic log whose start record names process ``pid``."""
    if not log_dir.is_dir():
        return None
    for path in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        with path.open(encoding="utf-8", errors="replace") as file:
            first = file.readline()
        start = first.find("{")
        if start < 0:
            continue
        try:
            data = json.loads(first[start:])
        except json.JSONDecodeError:
            continue
        if data.get("processId") == pid:
            return path
    return None


def az_json(config: dict, *args: str):
    result = subprocess.run(["az", *args, "--subscription", config["expected_subscription_id"], "-o", "json"],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:1000] or "Azure CLI command failed")
    return json.loads(result.stdout or "null")

def ensure_providers_registered(config: dict, providers: list[str] | tuple[str, ...], wait: bool = False, timeout_sec: int = 300) -> list[tuple[str, str]]:
    pending: list[tuple[str, str]] = []
    for namespace in providers:
        try:
            info = az_json(config, "provider", "show", "--namespace", namespace)
            state = str(info.get("registrationState") or "NotRegistered")
        except Exception:
            state = "NotRegistered"
        if state != "Registered":
            try:
                subprocess.run(
                    ["az", "provider", "register", "--namespace", namespace, "--subscription", config["expected_subscription_id"]],
                    capture_output=True, text=True, timeout=60,
                )
                if state == "NotRegistered":
                    state = "Registering"
            except Exception:
                pass
            pending.append((namespace, state))
    if wait and pending:
        deadline = time.monotonic() + timeout_sec
        remaining = [ns for ns, _ in pending]
        while remaining and time.monotonic() < deadline:
            still = []
            for namespace in remaining:
                try:
                    info = az_json(config, "provider", "show", "--namespace", namespace)
                    if info.get("registrationState") != "Registered":
                        still.append(namespace)
                except Exception:
                    still.append(namespace)
            remaining = still
            if remaining:
                time.sleep(5)
        if remaining:
            raise RuntimeError(f"Timed out waiting for Azure resource providers to reach Registered state: {', '.join(remaining)}")
    return pending

def _check_cardiology_region_quota(config: dict, location: str, candidates: list[tuple[str, str]]) -> str | None:
    offered = az_json(config, "cognitiveservices", "model", "list", "-l", location)
    usage = az_json(config, "cognitiveservices", "usage", "list", "-l", location)
    for name, version in candidates:
        available = any(m.get("model", {}).get("name") == name and m["model"].get("version") == version and
                        any(s.get("name") == "DataZoneStandard" for s in m["model"].get("skus", [])) for m in offered)
        quota = next((q for q in usage if q.get("name", {}).get("value") == f"OpenAI.DataZoneStandard.{name}"), {})
        free = float(quota.get("limit", 0)) - float(quota.get("currentValue", 0))
        if available and free >= 50:
            return f"{name} {version}: DataZoneStandard in {location}, {free:g}K TPM free"
    return None


class TransientHttpError(RuntimeError):
    """HTTP 429/5xx from a cloud API; ``retry_after`` is the server's Retry-After in seconds, if any."""

    def __init__(self, message: str, status: int, retry_after: float | None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


class Cloud:
    def __init__(self, config: dict):
        self.tokens = AzureCliTokens(config["expected_subscription_id"])
        self.expected_tenant = config["expected_tenant_id"]

    def request(self, method: str, url: str, resource: str = FABRIC, body=None, skill="search-consumption-cli"):
        token = self.tokens.token(resource)
        if self.tokens.tenant_id != self.expected_tenant:
            raise RuntimeError("Add-on token tenant differs from the deployment tenant")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if urllib.parse.urlsplit(url).hostname == "api.fabric.microsoft.com":
            headers["x-ms-fabric-skill"] = skill
        req = urllib.request.Request(url, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            return urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:800]
            message = f"{method} {url.split('?', 1)[0]} -> HTTP {error.code}: {detail}"
            if error.code == 429 or error.code >= 500:
                raise TransientHttpError(message, error.code, _retry_after_seconds(error.headers.get("Retry-After") if error.headers else None)) from None
            raise RuntimeError(message) from None

    def call(self, method: str, url: str, resource: str = FABRIC, body=None, skill="search-consumption-cli"):
        response = self.request(method, url, resource, body, skill)
        with response:
            raw = response.read()
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"{urllib.parse.urlsplit(url).hostname} returned a non-JSON API response") from exc

    def items(self, url: str, resource=FABRIC, skill="search-consumption-cli") -> list[dict]:
        values = []
        origin = urllib.parse.urlsplit(url).netloc
        while url:
            body = self.call("GET", url, resource, skill=skill)
            values.extend(body.get("value", []))
            continuation = body.get("continuationUri") or body.get("nextLink") or body.get("@odata.nextLink")
            if continuation and urllib.parse.urlsplit(continuation).netloc not in {"", origin}:
                raise RuntimeError("Cross-origin API continuation refused")
            url = urllib.parse.urljoin(url, continuation) if continuation else ""
        return values


def preflight(config: dict) -> list[dict]:
    checks = []

    def check(name, action):
        try:
            outcome = action()
            if isinstance(outcome, dict):
                status = outcome.get("status", "pass")
                detail = outcome.get("message") or outcome.get("detail") or ""
                checks.append({"name": name, "status": status, "message": detail, "detail": detail,
                               **{k: v for k, v in outcome.items() if k not in {"name", "status", "message", "detail"}}})
            else:
                checks.append({"name": name, "status": "pass", "message": outcome, "detail": outcome})
        except Exception as exc:
            checks.append({"name": name, "status": "fail", "message": str(exc), "detail": str(exc)})

    if config.get("deploy_databricks"):
        def databricks():
            provider = az_json(config, "provider", "show", "--namespace", "Microsoft.Databricks")
            reg_state = provider.get("registrationState")
            if reg_state != "Registered":
                ensure_providers_registered(config, ["Microsoft.Databricks"], wait=False)
            locations = Cloud(config).call("GET", f"{ARM}/subscriptions/{config['expected_subscription_id']}/locations?api-version=2022-12-01", ARM)["value"]
            region = next((x for x in locations if x["name"] == config["location"]), None)
            available = next((x.get("locations", []) for x in provider.get("resourceTypes", []) if x["resourceType"].lower() == "workspaces"), [])
            if not region or (available and region["displayName"] not in available):
                raise RuntimeError(f"Databricks workspaces are not offered in {config['location']}")
            missing = [x for x in ("azcopy", "databricks", "jq", "bash") if not shutil.which(x)]
            if missing:
                raise RuntimeError("Missing add-on tools: " + ", ".join(missing))
            if reg_state != "Registered":
                msg = f"Microsoft.Databricks is {reg_state or 'NotRegistered'}; auto-registration started and will complete in tandem with deployment."
                return {"status": "warn", "message": msg, "detail": msg}
            return "Databricks provider, region and tools ready; metastore account-admin access may require Continue"
        check("Databricks", databricks)
    if config.get("deploy_rayfin_apps"):
        def rayfin():
            if not shutil.which("node") or not shutil.which("npm"):
                raise RuntimeError("Rayfin requires Node.js and npm")
            return "Node.js and npm available"
        check("Rayfin apps", rayfin)
    if config.get("deploy_cardiology"):
        def model():
            pending_cardio = ensure_providers_registered(config, CARDIOLOGY_PROVIDERS, wait=False)
            location = config["cardiology_location"]
            candidates = [(config["cardiology_chat_model"], config["cardiology_chat_model_version"])] if config.get("cardiology_chat_model") else MODEL_CANDIDATES
            try:
                match = _check_cardiology_region_quota(config, location, candidates)
            except Exception as exc:
                if "MissingSubscriptionRegistration" in str(exc):
                    msg = "Microsoft.CognitiveServices is registering; auto-registration started and model quota will be verified once registration completes."
                    return {"status": "warn", "message": msg, "detail": msg}
                raise
            if match:
                return match
            suggested = ""
            for candidate_region in CARDIOLOGY_FALLBACK_REGIONS:
                if candidate_region == location:
                    continue
                try:
                    if _check_cardiology_region_quota(config, candidate_region, candidates):
                        suggested = candidate_region
                        break
                except Exception:
                    continue
            msg = f"No requested model/version offered as DataZoneStandard with >=50K TPM free in {location}" + (f" (available in {suggested})" if suggested else "")
            return {"status": "fail", "message": msg, "detail": msg,
                    **({"suggestedRegion": suggested} if suggested else {})}
        def registrations():
            cloud = Cloud(config)
            policy = cloud.call("GET", GRAPH + "/v1.0/policies/authorizationPolicy", GRAPH)
            if policy.get("defaultUserRolePermissions", {}).get("allowedToCreateApps"):
                return "Tenant permits users to create app registrations"
            memberships = cloud.items(GRAPH + "/v1.0/me/transitiveMemberOf/microsoft.graph.directoryRole", GRAPH)
            roles = {x.get("roleTemplateId") for x in memberships}
            if roles & {"62e90394-69f5-4237-9190-012177145e10", "cf1c38e5-3621-4004-a7cb-879624dced7c", "158c047a-c907-4556-b7ef-446551a6b5f7", "9b7fa17d-e63e-47b0-bb0a-15c516ac86ec"}:
                return "Directory role permits app registration creation"
            raise RuntimeError("App registration creation is disabled; ask an Entra admin to grant Application Developer or Application Administrator")
        check("Cardiology model quota", model)
        check("Cardiology app registrations", registrations)
    return checks


def require_one(values, description):
    if len(values) != 1:
        raise RuntimeError(f"Expected exactly one {description}, found {len(values)}")
    return values[0]

def parse_cli_json(output: str, description: str) -> dict:
    """Extract a JSON object from a CLI stream that may prefix informational lines."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"(?m)^[ \t]*\{", output):
        try:
            value, _ = decoder.raw_decode(output[match.start():].lstrip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(f"{description} returned no JSON object")



def prepare_bundle(bundle: dict, user: str) -> dict:
    """Adapt the Databricks bundle to deploy as the signed-in user instead of a service principal.

    Production targets refuse to validate without ``workspace.root_path`` once ``run_as`` is gone, so each
    gets the per-user path the Databricks CLI itself recommends.
    """
    for target in bundle["targets"].values():
        target.pop("run_as", None)
        if target.get("mode") == "production":
            target.setdefault("workspace", {})["root_path"] = f"/Workspace/Users/{user}/.bundle/" + "${bundle.name}/${bundle.target}"
    return bundle


class AddonRunner:
    def __init__(self, instance_id, config, deployment, save, pids):
        self.id, self.config, self.deployment = instance_id, config, deployment
        self.save, self.pids = save, pids
        self.cloud = Cloud(config)
        work_root = Path(os.environ.get("HLS_ADDON_WORK_DIR") or DATA_DIR / "addons")
        self.work = work_root / instance_id
        self.work.mkdir(parents=True, exist_ok=True)
        self.env = {**os.environ, "CI": "true", "HLS_NONINTERACTIVE": "1", "PYTHONUNBUFFERED": "1"}
        self.phase = None
        self.name = ""

    def persist(self):
        self.deployment["lastUpdatedTime"] = now()
        self.save()

    def log(self, text, level="info"):
        entry = {"timestamp": now(), "level": level, "message": text, "phase": self.phase["phase"] if self.phase else "Add-ons"}
        cs = self.deployment["customStatus"]
        cs["logs"] = (cs.get("logs", []) + [entry])[-100:]
        cs["detail"] = text
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f"{self.id}.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")
        self.persist()

    def substep(self, title, status, detail=""):
        steps = self.phase.setdefault("subSteps", [])
        step = next((s for s in steps if s["name"] == title), None)
        if step is None:
            step = {"name": title}
            steps.append(step)
        step.update(status=status, detail=detail, updatedAt=now())
        self.deployment["customStatus"].setdefault("subStepsByPhase", {})[self.phase["phase"]] = steps
        self.persist()

    async def command(self, title, args, cwd=None, env=None, capture=False, input_text=None, on_start=None):
        if self.deployment.get("runtimeStatus") == "Terminated":
            raise RuntimeError("Add-on cancelled")
        self.substep(title, "running")
        self.log(title)
        for arg in args[1:]:
            arg_str = str(arg)
            if arg_str.endswith((".py", ".sh", ".ps1")) and not arg_str.startswith("-"):
                script_path = Path(arg_str)
                if not script_path.is_absolute():
                    script_path = Path(cwd or ROOT) / script_path
                if not script_path.is_file():
                    err = FileNotFoundError(f"Script file not found: {script_path}")
                    self.substep(title, "failed", str(err))
                    raise err
                break
        process = await asyncio.create_subprocess_exec(*map(str, args), cwd=str(cwd or ROOT), env=env or self.env,
            stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE if capture else asyncio.subprocess.STDOUT,
            start_new_session=True)
        self.pids[self.id] = process.pid
        if on_start is not None:
            on_start(process.pid)
        script_name = next((Path(str(a)).name for a in args if str(a).endswith((".py", ".sh", ".ps1"))), Path(str(args[0])).name)
        try:
            if capture:
                output, errors = await process.communicate(input_text.encode() if input_text is not None else None)
                text = output.decode(errors="replace")
                if process.returncode:
                    raise RuntimeError(f"{title} ({script_name}): {errors.decode(errors='replace')[:1500]}")
            else:
                if input_text is not None:
                    process.stdin.write(input_text.encode())
                    await process.stdin.drain()
                    process.stdin.close()
                async for line in process.stdout:
                    self.log(line.decode(errors="replace").rstrip())
                await process.wait()
                text = ""
                if process.returncode:
                    raise RuntimeError(f"{title} ({script_name}) exited with code {process.returncode}")
            self.substep(title, "succeeded")
            return text
        except BaseException as exc:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGTERM)
                await process.wait()
            self.substep(title, "failed", str(exc))
            raise
        finally:
            self.pids.pop(self.id, None)

    async def rayfin_command(self, title, args, cwd, env, **kwargs):
        """Run `rayfin up` and keep its diagnostic log with this deployment (`up status` and `secret` write none)."""
        pids = []
        try:
            return await self.command(title, args, cwd, env, on_start=pids.append, **kwargs)
        finally:
            if pids:
                try:
                    await asyncio.to_thread(self.collect_rayfin_log, title, rayfin_log_dir(env), pids[0])
                except Exception as exc:
                    self.log(f"{title}: could not collect Rayfin CLI log: {exc}", "warn")

    def collect_rayfin_log(self, title, log_dir, pid):
        """Copy the CLI's (already sanitized) log to DATA_DIR and append its records to the run log."""
        source = rayfin_log_for_pid(log_dir, pid)
        if source is None:
            self.log(f"{title}: Rayfin CLI wrote no diagnostic log under {log_dir}", "warn")
            return
        target_dir = DATA_DIR / "logs" / "rayfin" / self.id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copyfile(source, target)
        phase = self.phase["phase"] if self.phase else "Add-ons"
        entries = []
        with target.open(encoding="utf-8", errors="replace") as file:
            for count, line in enumerate(file):
                if count == RAYFIN_LOG_LINE_LIMIT:
                    entries.append({"timestamp": now(), "level": "warn", "phase": phase, "source": "rayfin-cli",
                                    "message": f"[rayfin] log truncated after {RAYFIN_LOG_LINE_LIMIT} lines; full log: {target}"})
                    break
                parts = line.rstrip("\n").split(" ", 2)
                if len(parts) < 3:
                    continue
                timestamp, level, rest = parts
                entries.append({"timestamp": timestamp, "level": RAYFIN_LOG_LEVELS.get(level.lower(), "info"),
                                "phase": phase, "source": "rayfin-cli", "message": f"[rayfin] {rest}"})
        with (DATA_DIR / "logs" / f"{self.id}.jsonl").open("a", encoding="utf-8") as file:
            file.writelines(json.dumps(entry) + "\n" for entry in entries)
        self.log(f"{title}: Rayfin CLI log saved to {target}")

    async def ps(self, title, script, parameters):
        path = self.work / "parameters.json"
        path.write_text(json.dumps(parameters), encoding="utf-8")
        # Values are data in JSON, never interpolated as PowerShell source.
        code = "$p=Get-Content -Raw $env:HLS_ADDON_PARAMS|ConvertFrom-Json -AsHashtable; & $env:HLS_ADDON_SCRIPT @p; if($LASTEXITCODE){exit $LASTEXITCODE}"
        await self.command(title, ["pwsh", "-NoProfile", "-NonInteractive", "-Command", code],
                           env={**self.env, "HLS_ADDON_PARAMS": str(path), "HLS_ADDON_SCRIPT": str(script)})

    async def discover(self):
        config = self.config
        resources = await asyncio.to_thread(az_json, config, "resource", "list", "-g", config["resource_group_name"])
        self.azure = resources
        workspaces = await asyncio.to_thread(self.cloud.items, FABRIC + "/v1/workspaces")
        self.workspace = require_one([w for w in workspaces if w["displayName"] == config["fabric_workspace_name"]], "Fabric workspace")
        self.ws = self.workspace["id"]
        self.items = await asyncio.to_thread(self.cloud.items, f"{FABRIC}/v1/workspaces/{self.ws}/items")

    def resource(self, kind):
        return require_one([r for r in self.azure if r["type"].lower() == kind.lower()], kind)
    def item(self, kind, name):
        return require_one([i for i in self.items if i["type"] == kind and i["displayName"] == name], name)

    def _deployer_upn(self) -> str:
        """Resolve the signed-in user's UPN from the pinned subscription's ARM token claims."""
        try:
            payload = self.cloud.tokens.token(ARM).split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except Exception:
            return ""
        for key in ("upn", "preferred_username", "unique_name", "email"):
            value = claims.get(key)
            if isinstance(value, str) and "@" in value:
                return value.strip()
        return ""

    async def verify_silver_tcga_patients(self) -> int:
        """Verify the HDS Silver Lakehouse SQL endpoint has at least one seeded TCGA patient."""
        silver = require_one(
            [i for i in self.items if i.get("type") == "Lakehouse" and str(i.get("displayName") or "").lower().endswith("_silver")],
            "Silver Lakehouse",
        )
        detail = await asyncio.to_thread(self.cloud.call, "GET", f"{FABRIC}/v1/workspaces/{self.ws}/lakehouses/{silver['id']}")
        sql = (detail.get("properties") or {}).get("sqlEndpointProperties") or {}
        host = sql.get("connectionString")
        if not host:
            raise RuntimeError("Silver Lakehouse SQL endpoint is not provisioned")
        token = await asyncio.to_thread(self.cloud.tokens.token, "https://database.windows.net")
        # HDS Silver flattens FHIR arrays to *_string JSON columns; seed_tcga_cohort.py tags each
        # TCGA Patient with an identifier in the GDC barcode system.
        query = "SELECT COUNT(*) FROM dbo.Patient WHERE identifier_string LIKE '%gdc.cancer.gov/tcga/barcode%'"

        def count_tcga() -> int:
            import pyodbc
            raw = token.encode("utf-16-le")
            conn = pyodbc.connect(
                f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={host};DATABASE={silver['displayName']};Encrypt=yes;",
                attrs_before={1256: struct.pack(f"<I{len(raw)}s", len(raw), raw)},  # SQL_COPT_SS_ACCESS_TOKEN
                timeout=60,
            )
            try:
                conn.timeout = 120
                return int(conn.cursor().execute(query).fetchone()[0])
            finally:
                conn.close()

        count = await asyncio.to_thread(count_tcga)
        if count <= 0:
            raise RuntimeError(f"Silver Lakehouse {silver['displayName']} dbo.Patient has 0 TCGA patients after FHIR export and HDS ingestion")
        self.log(f"Silver Lakehouse {silver['displayName']}: {count} TCGA patients", "info")
        return count
    async def gold(self):
        gold = self.item("Lakehouse", "healthcare1_reporting_gold")
        detail = await asyncio.to_thread(self.cloud.call, "GET", f"{FABRIC}/v1/workspaces/{self.ws}/lakehouses/{gold['id']}")
        sql = detail["properties"]["sqlEndpointProperties"]
        if not sql.get("connectionString") or not sql.get("id"):
            raise RuntimeError("Gold SQL endpoint is not provisioned")
        return gold, sql

    async def run_fabric_job(self, item_type: str, item_name: str, job_type: str, timeout_sec: int = 3600):
        item = self.item(item_type, item_name)
        skill = "spark-cli" if item_type == "Notebook" else "pipeline-migration"
        post_url = f"{FABRIC}/v1/workspaces/{self.ws}/items/{item['id']}/jobs/instances?jobType={job_type}"
        resp = await asyncio.to_thread(self.cloud.request, "POST", post_url, FABRIC, {}, skill)
        with resp:
            job_url = resp.headers.get("Location") if hasattr(resp, "headers") and resp.headers else None
            if not job_url:
                raw = resp.read() if hasattr(resp, "read") else b""
                body = json.loads(raw.decode("utf-8", errors="replace") or "{}") if raw else {}
                inst_id = body.get("id")
                if not inst_id:
                    raise RuntimeError(f"Fabric job {item_name} response omitted Location and job id")
                job_url = f"{FABRIC}/v1/workspaces/{self.ws}/items/{item['id']}/jobs/instances/{inst_id}"
        deadline = time.monotonic() + timeout_sec
        transient = 0
        while True:
            if self.deployment.get("runtimeStatus") == "Terminated":
                raise RuntimeError(f"Add-on cancelled while running {item_name}")
            try:
                data = await asyncio.to_thread(self.cloud.call, "GET", job_url, FABRIC, None, skill)
            except (TransientHttpError, urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                # Throttling, 5xx and network blips are expected over an hour-long poll: back off and keep
                # polling until the job's own deadline instead of abandoning a running job.
                transient += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"Fabric job {item_name} status unknown at its {timeout_sec}s deadline: {exc}") from exc
                hinted = getattr(exc, "retry_after", None)
                delay = min(remaining, hinted if hinted is not None else min(10 * 2 ** (transient - 1), 120))
                self.log(f"Polling Fabric job {item_name} failed transiently ({exc}); retrying in {delay:.0f}s", "warn")
                await asyncio.sleep(delay)
                continue
            transient = 0
            status = str(data.get("status") or "").lower()
            if status in {"completed", "succeeded"}:
                return data
            if status in {"failed", "cancelled", "canceled", "deduped"}:
                reason = data.get("failureReason") or data
                raise RuntimeError(f"Fabric job {item_name} failed: {reason}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Fabric job {item_name} timed out after {timeout_sec}s")
            await asyncio.sleep(10)

    async def refresh_gold_sql_metadata(self):
        gold, sql = await self.gold()
        url = f"{FABRIC}/v1/workspaces/{self.ws}/sqlEndpoints/{sql['id']}/refreshMetadata"
        await asyncio.to_thread(self.cloud.call, "POST", url, FABRIC, {}, "sqldw-cli")

    async def ensure_eventstream_running(self, display_name: str) -> None:
        """Resume a paused base-deployment Eventstream before an add-on consumes it."""
        eventstream = self.item("Eventstream", display_name)
        url = f"{FABRIC}/v1/workspaces/{self.ws}/eventstreams/{eventstream['id']}"

        async def topology() -> dict:
            return await asyncio.to_thread(
                self.cloud.call, "GET", url + "/topology", FABRIC, None, "eventstream-cli",
            )

        def states(value: dict) -> list[dict]:
            nodes = [*(value.get("sources") or []), *(value.get("destinations") or [])]
            if not nodes:
                raise RuntimeError(f"{display_name} has no source or destination nodes")
            return nodes

        current = await topology()
        nodes = states(current)
        if all(node.get("status") == "Running" for node in nodes):
            return
        if any(node.get("status") == "Paused" for node in nodes):
            self.substep(f"Resume {display_name}", "running")
            await asyncio.to_thread(
                self.cloud.call, "POST", url + "/resume", FABRIC,
                {"startType": "WhenLastStopped"}, "eventstream-cli",
            )

        deadline = time.monotonic() + 600
        while True:
            current = await topology()
            nodes = states(current)
            if all(node.get("status") == "Running" for node in nodes):
                self.substep(f"Resume {display_name}", "succeeded")
                return
            failed = [node for node in nodes if node.get("status") in {"Failed", "Error"}]
            if failed:
                detail = "; ".join(
                    f"{node.get('name', 'node')}: {node.get('error') or node.get('status')}" for node in failed
                )
                raise RuntimeError(f"{display_name} failed to resume: {detail}")
            if time.monotonic() >= deadline:
                waiting = ", ".join(f"{node.get('name')}: {node.get('status')}" for node in nodes)
                raise RuntimeError(f"{display_name} did not resume within 10 minutes ({waiting})")
            await asyncio.sleep(10)


    async def run(self, addons, fresh_export=False, _reloaded=False):
        """Run each add-on independently: one failing add-on never prevents the others from running."""
        cs = self.deployment["customStatus"]
        if os.environ.get("HLS_HOSTED") == "1" and not _reloaded:
            # Only new tars from this sandbox's own data dir whose marker matches the image commit; boot
            # already re-applied earlier ones. An unpack failure raises HotfixError and fails the run.
            if await asyncio.to_thread(apply_hotfixes, DATA_DIR, default_targets(), reapply_applied=False):
                import importlib
                mod = importlib.reload(sys.modules[__name__])
                if mod.AddonRunner is not self.__class__:
                    return await mod.AddonRunner(self.id, self.config, self.deployment, self.save, self.pids).run(addons, fresh_export=fresh_export, _reloaded=True)
        await self.discover()
        failures = []
        for name in addons:
            self.name = name
            self.phase = {"phase": f"Add-on: {name.title()}", "status": "running", "subSteps": []}
            if not self.deployment.get("output"):
                self.deployment["output"] = {"phases": [], "resources": {}}
            self.deployment["output"].setdefault("phases", []).append(self.phase)
            cs["currentPhase"] = self.phase["phase"]
            state = cs.setdefault("addons", {}).setdefault(name, {})
            state.update(status="running", detail="Starting", startedAt=now())
            self.persist()
            start = time.monotonic()
            try:
                result = await getattr(self, name)(fresh_export=fresh_export)
                state.update(status="succeeded", detail="Deployment completed", resources=result, finishedAt=now())
                self.phase.update(status="succeeded", duration=f"{(time.monotonic()-start)/60:.1f} min")
                cs["completedPhases"] = sum(p.get("status") == "succeeded" for p in self.deployment["output"]["phases"])
            except BaseException as exc:
                state.update(status="failed", detail=str(exc), finishedAt=now())
                self.phase.update(status="failed", detail=str(exc))
                self.log(str(exc), "error")
                if not isinstance(exc, Exception) or self.deployment.get("runtimeStatus") == "Terminated":
                    raise
                failures.append(f"{name}: {exc}")
            finally:
                self.persist()
        if failures:
            raise RuntimeError("; ".join(failures))

    def working_copy(self, source, name):
        target = self.work / name
        if not target.exists():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("node_modules", "dist", ".git", ".env*", ".state", ".databricks", ".deployments.json", "*.tsbuildinfo", ".temp"))
        return target

    async def databricks(self, fresh_export=False):
        import yaml
        cfg = self.config
        await asyncio.to_thread(ensure_providers_registered, cfg, DATABRICKS_PROVIDERS, True, 300)
        root = self.working_copy(ROOT / "azure-databricks/implementation", "databricks")
        fhir = self.resource("Microsoft.HealthcareApis/workspaces/fhirservices")
        fhir_detail = await asyncio.to_thread(az_json, cfg, "resource", "show", "--ids", fhir["id"])
        storage = fhir_detail.get("properties", {}).get("exportConfiguration", {}).get("storageAccountName")
        if not storage:
            raise RuntimeError("FHIR export storage account is not configured")
        if fresh_export:
            await self.ps("Empty previous Databricks export", ROOT / "utilities/snapshot-fhir-export.ps1", {
                "ResourceGroupName": cfg["resource_group_name"], "SubscriptionId": cfg["expected_subscription_id"],
                "ClearSnapshotOnly": True})
            await self.ps("Fresh FHIR export for Databricks", ROOT / "phase-1/deploy-fhir.ps1", {
                "ResourceGroupName": cfg["resource_group_name"], "ExpectedSubscriptionId": cfg["expected_subscription_id"],
                "ExportOnly": True, "ExportContainerName": "fhir-export-databricks", "DeploymentPython": sys.executable})
        group = cfg.get("databricks_admin_group") or cfg["admin_security_group"]
        escaped_group = group.replace("'", "''")
        query = urllib.parse.urlencode({"$filter": f"displayName eq '{escaped_group}'", "$select": "id,displayName"})
        groups = await asyncio.to_thread(self.cloud.items, "https://graph.microsoft.com/v1.0/groups?" + query, "https://graph.microsoft.com")
        group_info = require_one(groups, "Databricks admin group in the deployment tenant")
        account = await asyncio.to_thread(az_json, cfg, "account", "show")
        variables = {
            "AZ_TENANT_ID": cfg["expected_tenant_id"], "ARM_TENANT_ID": cfg["expected_tenant_id"], "AZ_SUBSCRIPTION_ID": cfg["expected_subscription_id"],
            "AZ_RESOURCE_GROUP": cfg["resource_group_name"], "AZ_LOCATION": cfg["location"],
            "ADMIN_GROUP_OBJECT_ID": group_info["id"], "DATABRICKS_ADMIN_GROUP": group_info["displayName"],
            "STORAGE_ACCOUNT_NAME": storage, "EVENTHUB_NAMESPACE": self.resource("Microsoft.EventHub/namespaces")["name"],
            "KEY_VAULT_NAME": self.resource("Microsoft.KeyVault/vaults")["name"],
            "TELEMETRY_HUB": "telemetry-stream", "CLAIMS_HUB": "claim-stream",
            "TELEMETRY_CONSUMER_GROUP": "hls-dbx-telemetry", "CLAIMS_CONSUMER_GROUP": "hls-dbx-claims",
            "DATABRICKS_LISTEN_POLICY": "hls-databricks-listen", "EVENTHUB_SECRET_SCOPE": "hls-eventhubs", "EVENTHUB_SECRET_KEY": "listen-key",
            "ENVIRONMENT": cfg["databricks_environment"], "DATABRICKS_NAMESPACE": storage.lower(),
            "DATABRICKS_AUTH_TYPE": "azure-cli", "HLS_NONINTERACTIVE": "1",
            "FHIR_EXPORT_CONTAINER": "fhir-export-databricks", "FHIR_EXPORT_URL": f"abfss://fhir-export-databricks@{storage}.dfs.core.windows.net",
            "WORKLOAD_PRINCIPAL": account["user"]["name"], "ALERT_EMAIL": cfg.get("alert_email", "")}
        # Hosted jobs use the authenticated deployer, not an unrelated service principal.
        bundle_path = root / "bundle/databricks.yml"
        bundle = yaml.safe_load(bundle_path.read_text())
        prepare_bundle(bundle, account["user"]["name"])
        bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))
        def save_env():
            path = root / "env.sh"
            path.write_text("\n".join(f"export {key}={shlex.quote(str(value))}" for key, value in variables.items()) + "\n")
            path.chmod(0o600)
        save_env()
        env = {**self.env, **variables}
        scripts = root / "scripts"
        await self.command("01-preflight.sh", ["bash", scripts / "01-preflight.sh"], root, env)
        # Record any pre-existing workspace in the primary region before an eastus2 fallback creates a
        # second one: it is logged for operator teardown, never deleted automatically.
        orphan_workspaces: list[str] = []
        if cfg["location"].lower() != "eastus2":
            existing_ws = await asyncio.to_thread(az_json, cfg, "resource", "list", "-g", cfg["resource_group_name"], "--resource-type", "Microsoft.Databricks/workspaces")
            primary_ws = [w for w in existing_ws if w.get("location", "").lower() == cfg["location"].lower()]
            if cfg["location"].lower() == "westus2" and cfg.get("expected_tenant_id") == "c77e97fc-1859-4575-8c8b-53d74bc35a63":
                orphan_workspaces.extend(w["id"] for w in primary_ws if w.get("id"))
                variables["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
                env["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
                save_env()
            else:
                for w in primary_ws:
                    ws_full = await asyncio.to_thread(az_json, cfg, "resource", "show", "--ids", w["id"])
                    ws_url = ws_full.get("properties", {}).get("workspaceUrl", "")
                    if ws_url:
                        probe_env = {**env, "DATABRICKS_HOST": f"https://{ws_url}"}
                        try:
                            await self.command("Check existing Databricks workspace control plane", ["databricks", "current-user", "me", "-o", "json"], root, probe_env, capture=True)
                        except RuntimeError as probe_exc:
                            if "Did not find workspace with specified org ID" in str(probe_exc):
                                self.log(f"Existing {cfg['location']} workspace {w['name']} ({w['id']}) is not registered on the regional control plane; switching workspace target to eastus2 (orphan kept for teardown)...", "warn")
                                orphan_workspaces.append(w["id"])
                                variables["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
                                env["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
                                save_env()
                                break
        try:
            await self.command("02-deploy-databricks-foundation.sh", ["bash", scripts / "02-deploy-databricks-foundation.sh"], root, env)
        except RuntimeError:
            if cfg["location"].lower() != "eastus2" and env.get("DATABRICKS_WORKSPACE_LOCATION") != "eastus2":
                existing_ws = await asyncio.to_thread(az_json, cfg, "resource", "list", "-g", cfg["resource_group_name"], "--resource-type", "Microsoft.Databricks/workspaces")
                orphan_workspaces.extend(w["id"] for w in existing_ws if w.get("location", "").lower() == cfg["location"].lower() and w.get("id") and w["id"] not in orphan_workspaces)
                self.log(f"02-deploy-databricks-foundation.sh failed on existing {cfg['location']} workspace; deploying workspace in eastus2...", "warn")
                variables["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
                env["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
                save_env()
                await self.command("02-deploy-databricks-foundation.sh (eastus2 fallback)", ["bash", scripts / "02-deploy-databricks-foundation.sh"], root, env)
            else:
                raise
        def load_foundation():
            foundation = json.loads((root / f".state/foundation-{variables['ENVIRONMENT']}.json").read_text())
            for key, output in (("DATABRICKS_HOST", "workspaceUrl"), ("ACCESS_CONNECTOR_ID", "accessConnectorId"),
                                ("MANAGED_LOCATION_URL", "managedLocationUrl"), ("DICOM_OUTPUT_URL", "dicomOutputUrl")):
                variables[key] = foundation[output]["value"]
            for key, output in (("DATABRICKS_WORKSPACE_RESOURCE_ID", "workspaceId"), ("DATABRICKS_WORKSPACE_NAME", "workspaceName"),
                                ("ACCESS_CONNECTOR_PRINCIPAL_ID", "accessConnectorPrincipalId")):
                if isinstance(foundation.get(output), dict) and foundation[output].get("value"):
                    variables[key] = foundation[output]["value"]
            env.update(variables)
            save_env()
            # Persist the resolved workspaceUrl immediately so the add-on record names the live workspace
            # even if a later step (metastore pause, bundle, or interop verification) is still running.
            state_res = (
                self.deployment.setdefault("customStatus", {})
                .setdefault("addons", {})
                .setdefault("databricks", {})
                .setdefault("resources", {})
            )
            state_res["workspaceUrl"] = variables["DATABRICKS_HOST"]
            state_res["fhirExportUrl"] = variables["FHIR_EXPORT_URL"]
            if orphan_workspaces:
                state_res["orphanWorkspaces"] = list(dict.fromkeys(orphan_workspaces))
            self.persist()
            return foundation
        foundation = load_foundation()
        await self.ensure_metastore(env, root, variables, save_env, load_foundation, scripts, orphan_workspaces)
        await self.ensure_admin_group(env, root, variables["ADMIN_GROUP_OBJECT_ID"], variables["DATABRICKS_ADMIN_GROUP"])
        onelake_url = await self.ensure_onelake_databricks_storage(cfg, variables["ACCESS_CONNECTOR_ID"])
        if onelake_url:
            variables["ONELAKE_EXTERNAL_LOCATION_URL"] = onelake_url
            env["ONELAKE_EXTERNAL_LOCATION_URL"] = onelake_url
        env["ALERT_EMAIL"] = variables["ALERT_EMAIL"] = await self.databricks_alert_recipient(env, root, variables["ALERT_EMAIL"])
        save_env()
        for step in ("03-configure-eventhubs-access.sh", "04-unity-catalog-bootstrap.sh", "05-deploy-bundle.sh", "06-run-and-gate.sh"):
            await self.command(step, ["bash", scripts / step], root, env)
            if step == "04-unity-catalog-bootstrap.sh":
                env["WAREHOUSE_ID"] = json.loads((root / f".state/warehouse-{variables['ENVIRONMENT']}.json").read_text())["warehouse_id"]
        await self.command("07 Databricks deployment validation", [sys.executable, scripts / "07-validate-deployment.py", "--environment", variables["ENVIRONMENT"], "--namespace", variables["DATABRICKS_NAMESPACE"]], root, env)
        interop_flag = self.config.get("verify_databricks_interop", True)
        interop_enabled = interop_flag is True or (isinstance(interop_flag, str) and interop_flag.strip().lower() in ("true", "1", "yes")) if interop_flag is not None else True
        interop_title = "databricks: verify OneLake Unity Catalog interop"
        if interop_enabled:
            # discover() ran before earlier add-ons in this run; rayfin-imaging creates these
            # Lakehouses after it, so the snapshot taken at start cannot see them.
            self.items = await asyncio.to_thread(self.cloud.items, f"{FABRIC}/v1/workspaces/{self.ws}/items")
            names = ("clinical_lakehouse", "imaging_lakehouse", "patient360")
            missing = [n for n in names if not any(i["type"] == "Lakehouse" and i["displayName"] == n for i in self.items)]
            if missing:
                detail = f"skipped: rayfin-imaging Lakehouses not found ({', '.join(missing)}); deploy the rayfin add-on, then rerun databricks"
                self.substep(interop_title, "skipped", detail)
                self.log(f"{interop_title} {detail}", "warn")
            else:
                clinical_id, imaging_id, patient360_id = (self.item("Lakehouse", n)["id"] for n in names)
                await self.command(
                    interop_title,
                    [
                        sys.executable,
                        str(ROOT / "azure-databricks/implementation/scripts/09-onelake-interop-proof.py"),
                        "--live",
                        "--workspace-id", self.ws,
                        "--clinical-id", clinical_id,
                        "--imaging-id", imaging_id,
                        "--patient360-id", patient360_id,
                        "--access-connector-id", variables["ACCESS_CONNECTOR_ID"],
                        "--tenant-id", cfg["expected_tenant_id"],
                        "--namespace", variables["DATABRICKS_NAMESPACE"],
                    ],
                    root,
                    env,
                )
        return {
            "workspaceUrl": variables["DATABRICKS_HOST"],
            "fhirExportUrl": variables["FHIR_EXPORT_URL"],
            **({"onelakeExternalLocationUrl": onelake_url} if onelake_url else {}),
            **({"orphanWorkspaces": list(dict.fromkeys(orphan_workspaces))} if orphan_workspaces else {}),
        }

    async def ensure_onelake_databricks_storage(self, cfg, access_connector_id):
        """Provision Fabric AzureDatabricksStorage item, grant Access Connector MI Viewer + OneLake ReadWrite, and return ID-based ABFSS URL."""
        try:
            ac_detail = await asyncio.to_thread(az_json, cfg, "resource", "show", "--ids", access_connector_id)
            principal_id = (ac_detail.get("identity") or {}).get("principalId")
            if not principal_id:
                return ""
            roles = await asyncio.to_thread(self.cloud.items, f"{FABRIC}/v1/workspaces/{self.ws}/roleAssignments", FABRIC, "onelake-catalog-govern-cli")
            if not any((r.get("principal") or {}).get("id") == principal_id for r in roles):
                await asyncio.to_thread(
                    self.cloud.call, "POST", f"{FABRIC}/v1/workspaces/{self.ws}/roleAssignments", FABRIC,
                    {"principal": {"id": principal_id, "type": "ServicePrincipal"}, "role": "Viewer"},
                    "onelake-catalog-govern-cli",
                )
            items = await asyncio.to_thread(self.cloud.items, f"{FABRIC}/v1/workspaces/{self.ws}/items", FABRIC, "search-consumption-cli")
            storage_item = next((i for i in items if i.get("displayName") == "hls_databricks_onelake_storage"), None)
            if not storage_item:
                storage_item = await asyncio.to_thread(
                    self.cloud.call, "POST", f"{FABRIC}/v1/workspaces/{self.ws}/items", FABRIC,
                    {"displayName": "hls_databricks_onelake_storage", "type": "DatabricksStorage", "description": "OneLake external location storage item for Azure Databricks Unity Catalog"},
                    "onelake-catalog-govern-cli",
                )
            item_id = storage_item["id"]
            dar_payload = {
                "value": [{
                    "name": "DatabricksUnityCatalogAccess",
                    "decisionRules": [{
                        "effect": "Permit",
                        "permission": [
                            {"attributeName": "Path", "attributeValueIncludedIn": ["*"]},
                            {"attributeName": "Action", "attributeValueIncludedIn": ["ReadWrite"]},
                        ],
                    }],
                    "members": {
                        "microsoftEntraMembers": [{"objectId": principal_id, "tenantId": cfg["expected_tenant_id"]}],
                    },
                }],
            }
            await asyncio.to_thread(
                self.cloud.call, "PUT", f"{FABRIC}/v1/workspaces/{self.ws}/items/{item_id}/dataAccessRoles",
                FABRIC, dar_payload, "onelake-catalog-govern-cli",
            )
            return f"abfss://{self.ws}@onelake.dfs.fabric.microsoft.com/{item_id}/Files/"
        except Exception as exc:
            self.log(f"Optional OneLake external location provisioning skipped: {exc}", "warn")
            return ""
    async def databricks_alert_recipient(self, env, root, email):
        """Return ``email`` only if it is a user of the Databricks workspace, else an empty string.

        The deployment's alert recipient is also the Fabric Activator recipient and may be any mailbox, but a
        Databricks alert subscription must name a workspace user: otherwise the bundle fails with "Failed to get
        user id for email". Empty keeps the alert PAUSED with no recipient, which the scripts already support.
        """
        if not email:
            return ""
        escaped = email.replace('"', "")
        found = json.loads(await self.command("Check Databricks alert recipient",
                                              ["databricks", "users", "list", "--filter", f'userName eq "{escaped}"', "-o", "json"],
                                              root, env, capture=True) or "[]")
        if found:
            return email
        self.log(f"{email} is not a Databricks workspace user, so the Databricks clinical alert is deployed paused with no recipient.", "warning")
        return ""

    async def ensure_admin_group(self, env, root, object_id, name):
        """Provision the Entra admin group into the Databricks account so Unity Catalog grants can name it.

        Uses the supported external-group API. It needs Automatic Identity Management, which Databricks
        enables by default only for accounts created after 2025-08-01 and exposes no public setting API.
        """
        try:
            await self.command(f"Provision Entra group {name} into Databricks",
                               ["databricks", "workspace-iam-v2", "resolve-group-proxy", object_id, "-o", "json"],
                               root, env, capture=True)
        except RuntimeError as exc:
            if "Automatic Identity Management is not enabled" in str(exc):
                raise RuntimeError(
                    f"Entra group {name} cannot be provisioned: Automatic Identity Management is off for this Databricks "
                    "account. An account admin must turn on Security -> Identity provider setup -> Automatic Identity "
                    "Management in https://accounts.azuredatabricks.net (takes 5-10 minutes), then add the Databricks add-on again. "
                    "The completed base deployment is unaffected.") from exc
            raise

    async def _databricks_workspace_id(self, variables: dict | None, ws_loc: str) -> tuple[str, str]:
        """Return ``(numeric_workspace_id, arm_resource_id)`` for the target Databricks workspace."""
        vars_map = variables or {}
        arm_id = vars_map.get("DATABRICKS_WORKSPACE_RESOURCE_ID", "")
        expected_name = vars_map.get("DATABRICKS_WORKSPACE_NAME", "")
        if not expected_name and vars_map.get("STORAGE_ACCOUNT_NAME") and vars_map.get("ENVIRONMENT"):
            suffix = f"-{ws_loc}-ws" if ws_loc.lower() != self.config["location"].lower() else "-ws"
            expected_name = f"hls-{vars_map['STORAGE_ACCOUNT_NAME']}-{vars_map['ENVIRONMENT']}{suffix}"
        if arm_id:
            detail = await asyncio.to_thread(az_json, self.config, "resource", "show", "--ids", arm_id)
            return str(detail["properties"]["workspaceId"]), arm_id
        candidates = [r for r in self.azure if r["type"].lower() == "microsoft.databricks/workspaces"]
        if not candidates or (expected_name and not any(r.get("name") == expected_name for r in candidates)):
            candidates = await asyncio.to_thread(
                az_json, self.config, "resource", "list", "-g", self.config["resource_group_name"],
                "--resource-type", "Microsoft.Databricks/workspaces",
            )
        by_name = [r for r in candidates if expected_name and r.get("name") == expected_name]
        by_loc = [r for r in candidates if (r.get("location") or "").lower() == ws_loc.lower()]
        dbx = by_name[0] if len(by_name) == 1 else (by_loc[0] if len(by_loc) == 1 else require_one(by_name or by_loc or candidates, "Databricks workspace"))
        workspace_id = dbx.get("workspaceId") or (dbx.get("properties") or {}).get("workspaceId")
        if not workspace_id:
            detail = await asyncio.to_thread(az_json, self.config, "resource", "show", "--ids", dbx["id"])
            workspace_id = detail["properties"]["workspaceId"]
        return str(workspace_id), dbx["id"]

    async def _assign_regional_metastore(self, env, root, variables: dict | None, ws_loc: str) -> str:
        data = json.loads(await self.command("List available Unity Catalog metastores", ["databricks", "metastores", "list", "-o", "json"], root, env, capture=True))
        candidates = data if isinstance(data, list) else data.get("metastores", [])
        metastore = require_one([m for m in candidates if m.get("region", "").replace(" ", "").lower() == ws_loc.lower()], "regional Databricks metastore")
        workspace_id, _ = await self._databricks_workspace_id(variables, ws_loc)
        await self.command("Assign regional Unity Catalog metastore", ["databricks", "metastores", "assign", workspace_id, metastore["metastore_id"], "hive_metastore", "-o", "json"], root, env)
        return workspace_id

    async def ensure_metastore(self, env, root, variables=None, save_env=None, load_foundation=None, scripts=None, orphan_workspaces=None):
        async def assigned():
            try:
                result = json.loads(await self.command("Check Unity Catalog metastore", ["databricks", "metastores", "current", "-o", "json"], root, env, capture=True))
                return bool(result.get("metastore_id"))
            except RuntimeError:
                return False
        if await assigned():
            return
        explanation = ""
        org_not_found = False
        ws_loc = (variables or {}).get("DATABRICKS_WORKSPACE_LOCATION") or self.config["location"]
        for attempt in range(1, 4):
            try:
                await self._assign_regional_metastore(env, root, variables, ws_loc)
                if await assigned():
                    return
                explanation = "Assignment is not yet visible."
                break
            except (urllib.error.HTTPError, RuntimeError, KeyError) as exc:
                explanation = f"Automatic metastore assignment unavailable: {exc}."
                if "Did not find workspace with specified org ID" in str(exc):
                    org_not_found = True
                    if attempt < 3:
                        self.log(f"Databricks workspace org ID not yet propagated to regional control plane; retrying in 15s ({attempt}/3)...", "warn")
                        await asyncio.sleep(15)
                        continue
                break
        if org_not_found and self.config["location"].lower() != "eastus2" and variables is not None and save_env is not None and load_foundation is not None and scripts is not None:
            orphan_id = variables.get("DATABRICKS_WORKSPACE_RESOURCE_ID")
            if not orphan_id:
                for r in self.azure:
                    if r["type"].lower() == "microsoft.databricks/workspaces" and (r.get("location") or "").lower() == self.config["location"].lower():
                        orphan_id = r.get("id")
                        break
            if orphan_id:
                if orphan_workspaces is not None and orphan_id not in orphan_workspaces:
                    orphan_workspaces.append(orphan_id)
                self.log(f"Recording orphan {self.config['location']} Databricks workspace {orphan_id} for teardown (not deleted automatically).", "warn")
            self.log(f"Databricks regional control plane in {self.config['location']} did not register the workspace org ID; deploying workspace in eastus2 (Access Connector remains in {self.config['location']})...", "warn")
            variables["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
            env["DATABRICKS_WORKSPACE_LOCATION"] = "eastus2"
            save_env()
            await self.command("02-deploy-databricks-foundation.sh (eastus2 fallback)", ["bash", scripts / "02-deploy-databricks-foundation.sh"], root, env)
            load_foundation()
            try:
                await self._assign_regional_metastore(env, root, variables, "eastus2")
            except (urllib.error.HTTPError, RuntimeError, KeyError) as exc:
                explanation = f"Automatic eastus2 metastore assignment unavailable: {exc}."
            if await assigned():
                return
        event = CONTINUATIONS.setdefault(self.id, asyncio.Event())
        deadline = time.monotonic() + 24 * 3600
        state = self.deployment["customStatus"]["addons"]["databricks"]
        try:
            while True:
                state.update(status="paused", detail=f"{explanation} Ask a Databricks account admin to open https://accounts.azuredatabricks.net, select Catalog → Metastores → the {self.config['location']} metastore, and assign workspace {env['DATABRICKS_HOST']}. Then select Continue within 24 hours.")
                self.substep("Unity Catalog metastore assignment", "pending", state["detail"])
                self.log(state["detail"], "warn")
                event.clear()
                while not event.is_set():
                    if self.deployment.get("runtimeStatus") == "Terminated" or state.get("status") == "cancelled":
                        raise RuntimeError("Add-on cancelled while awaiting metastore assignment")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("Databricks metastore assignment timed out after 24 hours")
                    try:
                        await asyncio.wait_for(event.wait(), timeout=min(remaining, 30))
                    except asyncio.TimeoutError:
                        pass
                if state.get("status") == "cancelled":
                    raise RuntimeError("Add-on cancelled while awaiting metastore assignment")
                if await assigned():
                    state.update(status="running", detail="Metastore assigned; continuing")
                    self.substep("Unity Catalog metastore assignment", "succeeded")
                    return
                explanation = "The workspace still has no assigned metastore."
        finally:
            CONTINUATIONS.pop(self.id, None)

    async def rayfin(self, fresh_export=False):
        import yaml
        cfg = self.config
        gold, sql = await self.gold()
        result = {"goldSqlHost": sql["connectionString"], "goldDatabase": gold["displayName"]}
        existing_res = dict(((self.deployment.get("customStatus") or {}).get("addons") or {}).get("rayfin", {}).get("resources") or {})
        rayfin_apps = ("rayfin-health-command-center", "rayfin-clinical-triage-app", "rayfin-imaging", "rayfin-wardflow-persona-app")
        result.update({k: v for k, v in existing_res.items() if k in rayfin_apps and v})
        wardflow_root = Path(os.environ.get("WARDFLOW_ROOT", str(Path.home() / "git/.worktrees/wardflow-jb-dev")))
        for app in rayfin_apps:
            if result.get(app):
                self.log(f"{app}: reusing existing deployment {result[app]}", "info")
                continue
            app_source = ROOT / app if (ROOT / app).is_dir() else (wardflow_root / app)
            if not app_source.is_dir():
                if app == "rayfin-wardflow-persona-app":
                    self.log(f"{app}: source not present at {app_source}; skipping optional WardFlow persona app", "info")
                    continue
                raise RuntimeError(f"{app}: source directory not found at {app_source}")
            root = self.working_copy(app_source, app)
            if app == "rayfin-imaging" and (ROOT / app / "pipeline").is_dir():
                shutil.copytree(ROOT / app / "pipeline", root / "pipeline", dirs_exist_ok=True)
                shutil.copytree(ROOT / app / "scripts", root / "scripts", dirs_exist_ok=True)
                for fn_meta in ("host.json", "local.settings.json", "deploymetadata.json", "runtimemetadata.json"):
                    src_meta = ROOT / app / "rayfin/functions" / fn_meta
                    if src_meta.is_file():
                        shutil.copy(src_meta, root / "rayfin/functions" / fn_meta)
            config_path = root / "rayfin/rayfin.yml"
            config = yaml.safe_load(config_path.read_text())
            config.pop("publishable_key", None)
            config["services"]["auth"]["allowedRedirectUris"] = ["http://localhost:5173", "http://127.0.0.1:5173"]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            fabric_path = root / "fabric.yaml"
            if fabric_path.exists():
                fabric = yaml.safe_load(fabric_path.read_text())
                for profile in fabric["profiles"].values():
                    for alias, model in profile.get("semanticModels", {}).items():
                        name = {"popHealthGold": "Population Health & Quality Semantic Model", "imagingGold": "ImagingReport"}[alias]
                        model.update(workspaceId=self.ws, itemId=self.item("SemanticModel", name)["id"])
                    for lakehouse in profile.get("lakehouses", {}).values():
                        lakehouse.update(workspaceId=self.ws, itemId=gold["id"])
                fabric_path.write_text(yaml.safe_dump(fabric, sort_keys=False))
            await self.command(f"{app}: npm ci", ["npm", "ci", "--no-audit", "--no-fund"], root)
            # Management/up requires Fabric; DB/semantic-model probes require Power BI.
            # Never reuse one ambient token for commands requesting another audience.
            async def rayfin_env(resource=FABRIC):
                token = await asyncio.to_thread(self.cloud.tokens.token, resource)
                return {**self.env, "RAYFIN_TOKEN": token, "RAYFIN_WORKSPACE_ID": self.ws,
                        "RAYFIN_TENANT_ID": cfg["expected_tenant_id"], "SQL_HOST": sql["connectionString"], "GOLD_DATABASE": gold["displayName"]}
            cli = [str(root / "node_modules/.bin/rayfin")]
            up = cli + ["up", "--workspace-id", self.ws, "--tenant", cfg["expected_tenant_id"], "--yes"]
            # Provision first so `rayfin env` in the build has the new backend, not a source workspace.
            await self.rayfin_command(f"{app}: provision backend", up + ["--exclude-services", "staticHosting,functions"], root, await rayfin_env())
            if app == "rayfin-health-command-center":
                databases = await asyncio.to_thread(self.cloud.items, f"{FABRIC}/v1/workspaces/{self.ws}/sqlDatabases", FABRIC, "sqldb-cli")
                database = require_one([d for d in databases if d["displayName"] == app], "command center app SQL database")
                detail = await asyncio.to_thread(self.cloud.call, "GET", f"{FABRIC}/v1/workspaces/{self.ws}/sqlDatabases/{database['id']}", FABRIC, None, "sqldb-cli")
                properties = detail["properties"]
                sql_env = {**self.env, "SQL_SERVER": properties["serverFqdn"], "SQL_DATABASE": properties["databaseName"]}
                for key in ("SQL_SERVER", "SQL_DATABASE"):
                    await self.command(f"{app}: configure {key}", cli + ["secret", "set", key, "--stdin"], root, await rayfin_env(), input_text=sql_env[key])
                account = await asyncio.to_thread(az_json, cfg, "account", "show")
                sql_env.update(SQL_DEPLOYER_UPN=account["user"]["name"], SQL_ACCESS_TOKEN=await asyncio.to_thread(self.cloud.tokens.token, "https://database.windows.net"))
                await self.command(f"{app}: install function dependencies", ["npm", "ci", "--no-audit", "--no-fund"], root / "rayfin/functions")
                await self.command(f"{app}: configure publication boundary", ["node", root / "scripts/configure-publication.mjs"], root, sql_env)
            if app == "rayfin-imaging":
                await self.prepare_rayfin_imaging(root)
                await self.command(f"{app}: install function dependencies", ["npm", "ci", "--no-audit", "--no-fund"], root / "rayfin/functions")
            await self.command(f"{app}: build", ["npm", "run", "build"], root, await rayfin_env("https://analysis.windows.net/powerbi/api"))
            await self.rayfin_command(f"{app}: deploy", up, root, await rayfin_env())
            status = parse_cli_json(
                await self.command(f"{app}: hosting details", cli + ["up", "status", "--json"], root, await rayfin_env(), capture=True),
                f"{app} hosting status",
            )
            deployment = status.get("deployment", {})
            hosting = deployment.get("hostingUrl")
            if not hosting:
                raise RuntimeError(f"{app}: deployment returned no hosting origin")
            config = yaml.safe_load(config_path.read_text())
            origin = urllib.parse.urlsplit(hosting)
            origin = f"{origin.scheme}://{origin.netloc}"
            redirects = config["services"]["auth"].setdefault("allowedRedirectUris", [])
            if origin not in redirects:
                redirects.append(origin)
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            # CLI's hosting callback registration is best-effort. Reapply settings as a
            # required step, without rebuilding the two services a second time.
            await self.rayfin_command(f"{app}: register hosting origin", up + ["--exclude-services", "staticHosting,functions"], root, await rayfin_env())
            result[app] = hosting
            self.deployment.get("customStatus", {}).setdefault("addons", {}).setdefault("rayfin", {})["resources"] = dict(result)
            self.persist()
        cardio_res = ((self.deployment.get("customStatus") or {}).get("addons") or {}).get("cardiology", {}).get("resources") or {}
        if cardio_res.get("resourceGroup") and cardio_res.get("url"):
            try:
                cardio_prefix = cfg.get("cardiology_prefix") or "cardio" + re.sub("[^a-z0-9]", "", cfg["fabric_workspace_name"].lower())[-6:]
                env_args = [
                    f"CALDOVA_RAYFIN_IMAGING_URL={result.get('rayfin-imaging', '')}",
                    f"CALDOVA_RAYFIN_COMMAND_CENTER_URL={result.get('rayfin-health-command-center', '')}",
                    f"CALDOVA_RAYFIN_CLINICAL_TRIAGE_URL={result.get('rayfin-clinical-triage-app', '')}",
                ]
                await asyncio.to_thread(az, cfg, "containerapp", "update", "-g", cardio_res["resourceGroup"], "-n", cardio_prefix + "-app", "--set-env-vars", *env_args)
            except Exception as exc:
                self.log(f"Could not sync Rayfin URLs to cardiology Container App: {exc}", "warn")
        return result


    async def prepare_rayfin_imaging(self, root: Path):
        cfg = self.config
        ws_name = cfg["fabric_workspace_name"]
        await self.command("rayfin-imaging: setup imaging_lakehouse", [sys.executable, root / "scripts/setup_fabric.py", "--workspace", ws_name], root)
        shared_dir = os.environ.get("HLS_SHARED_DATA_DIR")
        default_slides = "brain-gbm,breast-brca,kidney-kirc" if os.environ.get("HLS_HOSTED") == "1" else ""
        slides_spec = ",".join(s.strip() for s in os.environ.get("HLS_RAYFIN_IMAGING_SLIDES", default_slides).split(",") if s.strip())
        datasets_spec = ",".join(d.strip() for d in os.environ.get("HLS_RAYFIN_IMAGING_DATASETS", "petct,lung4d,tracts,fetal").split(",") if d.strip())
        totalseg_spec = "0" if os.environ.get("HLS_RAYFIN_IMAGING_TOTALSEG", "1") == "0" else "1"
        cache_key = hashlib.sha256(f"slides={slides_spec}|datasets={datasets_spec}|totalseg={totalseg_spec}".encode("utf-8")).hexdigest()[:12]
        cache_dir = Path(shared_dir) / "rayfin-imaging-cache" / cache_key if os.environ.get("HLS_HOSTED") == "1" and shared_dir else None
        default_hosted = slides_spec == "brain-gbm,breast-brca,kidney-kirc" and datasets_spec == "petct,lung4d,tracts,fetal" and totalseg_spec == "1"
        legacy_cache = Path(shared_dir) / "rayfin-imaging-cache" if cache_dir and default_hosted else None
        seed_dir = next((d for d in (cache_dir, legacy_cache) if d and (d / "lakehouse/manifest.json").is_file() and (d / "volumes/manifest.json").is_file()), None)
        if seed_dir is not None:
            self.log(f"Seeding rayfin-imaging from internal shared cache ({seed_dir})...", "info")
            work_dir = root / "work"
            if work_dir.exists():
                shutil.rmtree(work_dir)
            shutil.copytree(seed_dir / "lakehouse", work_dir / "lakehouse")
            shutil.copytree(seed_dir / "volumes", work_dir / "volumes")
        else:
            py = root / ".venv/bin/python"
            if not py.is_file():
                await self.command("rayfin-imaging: create pipeline venv", [sys.executable, "-m", "venv", str(root / ".venv")], root)
                await self.command("rayfin-imaging: install pipeline requirements", [str(py), "-m", "pip", "install", "--no-cache-dir", "-r", str(root / "pipeline/requirements.txt")], root)
            if not (root / "work/lakehouse/manifest.json").is_file():
                shutil.rmtree(root / "work/raw", ignore_errors=True)
                slides_json = root / "pipeline/slides.json"
                all_slides = [s["id"] for s in json.loads(slides_json.read_text())] if slides_json.is_file() else []
                slides_arg = [s for s in slides_spec.split(",") if s] or all_slides
                if slides_arg:
                    for sid in slides_arg:
                        if (root / f"work/lakehouse/slides/{sid}/label.json").is_file():
                            continue
                        await self.command(f"rayfin-imaging: download slide {sid}", [str(py), str(root / "pipeline/download_slides.py"), "--only", sid], root)
                        await self.command(f"rayfin-imaging: tile slide {sid}", [str(py), str(root / "pipeline/generate_tiles.py"), "--raw", "work/raw", "--out", "work/lakehouse", "--only", sid], root)
                        shutil.rmtree(root / "work/raw", ignore_errors=True)
                    await self.command("rayfin-imaging: generate Deep Zoom tiles", [str(py), str(root / "pipeline/generate_tiles.py"), "--raw", "work/raw", "--out", "work/lakehouse", "--only", "none"], root)
                else:
                    await self.command("rayfin-imaging: download slides", [str(py), str(root / "pipeline/download_slides.py")], root)
                    await self.command("rayfin-imaging: generate Deep Zoom tiles", [str(py), str(root / "pipeline/generate_tiles.py"), "--raw", "work/raw", "--out", "work/lakehouse"], root)
            shutil.rmtree(root / "work/raw", ignore_errors=True)
            datasets = [d for d in datasets_spec.split(",") if d]
            for ds_key in datasets:
                if ds_key == "multiplex":
                    if not (root / "work/lakehouse/slides/colon-cycif/label.json").is_file():
                        await self.command(f"rayfin-imaging: download {ds_key}", [str(py), str(root / "pipeline/download_data.py"), ds_key], root)
                        await self.command("rayfin-imaging: build multiplex immunofluorescence", [str(py), str(root / "pipeline/build_multiplex.py")], root)
                        await self.command("rayfin-imaging: update slide manifest", [str(py), str(root / "pipeline/generate_tiles.py"), "--raw", "work/raw", "--out", "work/lakehouse", "--only", "none"], root)
                    shutil.rmtree(root / "work/mif", ignore_errors=True)
                elif ds_key == "petct":
                    if not (root / "work/volumes/petct-whole-body/study.json").is_file():
                        await self.command(f"rayfin-imaging: download {ds_key}", [str(py), str(root / "pipeline/download_data.py"), ds_key], root)
                        await self.command("rayfin-imaging: build_petct.py", [str(py), str(root / "pipeline/volumes/build_petct.py")], root)
                    shutil.rmtree(root / "work/petct", ignore_errors=True)
                elif ds_key == "lung4d":
                    if not (root / "work/volumes/lung-4dct/study.json").is_file():
                        await self.command(f"rayfin-imaging: download {ds_key}", [str(py), str(root / "pipeline/download_data.py"), ds_key], root)
                        await self.command("rayfin-imaging: build_lung4d.py", [str(py), str(root / "pipeline/volumes/build_lung4d.py")], root)
                    shutil.rmtree(root / "work/lung4d", ignore_errors=True)
                elif ds_key == "tracts":
                    if not (root / "work/volumes/brain-tractography/study.json").is_file():
                        await self.command(f"rayfin-imaging: download {ds_key}", [str(py), str(root / "pipeline/download_data.py"), ds_key], root)
                        await self.command("rayfin-imaging: build_tractography.py", [str(py), str(root / "pipeline/volumes/build_tractography.py")], root)
                    shutil.rmtree(root / "work/tracts", ignore_errors=True)
                elif ds_key == "fetal":
                    if not (root / "work/volumes/fetal-brain-atlas/study.json").is_file():
                        await self.command(f"rayfin-imaging: download {ds_key}", [str(py), str(root / "pipeline/download_data.py"), ds_key], root)
                        for builder in ("build_fetal_face.py", "build_fetal_body.py", "build_fetal_atlas.py"):
                            await self.command(f"rayfin-imaging: {builder}", [str(py), str(root / "pipeline/volumes" / builder)], root)
                    for d_tmp in ("fetal_face", "fetal_body", "fetal_dhcp"):
                        shutil.rmtree(root / "work" / d_tmp, ignore_errors=True)
                elif ds_key == "vhp":
                    if not (root / "work/volumes/visible-human-body/study.json").is_file():
                        await self.command(f"rayfin-imaging: download {ds_key}", [str(py), str(root / "pipeline/download_data.py"), ds_key], root)
                        await self.command("rayfin-imaging: build_visible_human.py", [str(py), str(root / "pipeline/volumes/build_visible_human.py")], root)
                    shutil.rmtree(root / "work/vhp", ignore_errors=True)
            if totalseg_spec != "0":
                if not (root / "work/volumes/totalseg-ct-angio/study.json").is_file():
                    await self.command("rayfin-imaging: build_totalseg.py", [str(py), str(root / "pipeline/volumes/build_totalseg.py")], root)
                shutil.rmtree(root / "work/totalseg", ignore_errors=True)
            await self.command("rayfin-imaging: build_mip.py", [str(py), str(root / "pipeline/volumes/build_mip.py")], root)
            await self.command("rayfin-imaging: build initial volume manifest", [str(py), str(root / "pipeline/volumes/build_manifest.py")], root)
            if cache_dir is not None:
                staging: Path | None = None
                try:
                    cache_dir.parent.mkdir(parents=True, exist_ok=True)
                    staging = Path(tempfile.mkdtemp(prefix=f".{cache_dir.name}-tmp-", dir=str(cache_dir.parent)))
                    shutil.copytree(root / "work/lakehouse", staging / "lakehouse")
                    shutil.copytree(root / "work/volumes", staging / "volumes")
                    if not cache_dir.exists():
                        os.replace(staging, cache_dir)
                        staging = None
                    self.log(f"Populated internal shared cache at {cache_dir} for subsequent deployments.", "info")
                except Exception as cache_exc:
                    self.log(f"Could not populate internal shared cache: {cache_exc}", "warn")
                finally:
                    if staging is not None:
                        shutil.rmtree(staging, ignore_errors=True)
        try:
            storage = self.resource("Microsoft.Storage/storageAccounts")["name"]
            cohort_py = root / ".venv/bin/python"
            if not cohort_py.is_file():
                try:
                    subprocess.check_call([sys.executable, "-c", "import numpy, pydicom, SimpleITK, PIL"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    cohort_py = Path(sys.executable)
                except Exception:
                    await self.command("rayfin-imaging: create cohort DICOM venv", [sys.executable, "-m", "venv", str(root / ".venv")], root)
                    await self.command("rayfin-imaging: install cohort DICOM requirements", [str(cohort_py), "-m", "pip", "install", "--no-cache-dir", "numpy", "pydicom", "SimpleITK", "Pillow"], root)
            await self.command("rayfin-imaging: convert cohort DICOM studies to NIfTI", [
                str(cohort_py), str(root / "pipeline/volumes/build_cohort_dicom.py"), "--storage-account", storage, "--limit", "3",
            ], root)
        except Exception as exc:
            self.log(f"Cohort DICOM-to-NIfTI optional bridge skipped: {exc}", "warn")
        await self.command("rayfin-imaging: build volume manifest", [sys.executable, str(root / "pipeline/volumes/build_manifest.py")], root)
        await self.command("rayfin-imaging: upload slides to OneLake", ["bash", str(root / "pipeline/upload_to_onelake.sh")], root)
        await self.command("rayfin-imaging: register slides Delta table", [sys.executable, str(root / "pipeline/register_catalog_table.py")], root)
        await self.command("rayfin-imaging: upload volumes to OneLake", ["bash", str(root / "pipeline/volumes/upload_volumes.sh")], root)
        await self.command("rayfin-imaging: register volumes Delta table", [sys.executable, str(root / "pipeline/volumes/register_volume_table.py")], root)
        if (root / "pipeline/seed_patient360_silos.py").is_file():
            await self.command("rayfin-imaging: seed Patient 360 silos and shortcuts", [sys.executable, str(root / "pipeline/seed_patient360_silos.py")], root)
        if (root / "pipeline/seed_patient360_silos.py").is_file() or cfg.get("resource_group_name"):
            # 1. TCGA Synthetic FHIR cohort seeding (ticket 002, default True)
            tcga_flag = self.config.get("seed_tcga_cohort", True)
            tcga_enabled = tcga_flag is True or (isinstance(tcga_flag, str) and tcga_flag.strip().lower() in ("true", "1", "yes")) if tcga_flag is not None else True
            if tcga_enabled:
                await self.command(
                    "rayfin-imaging: seed TCGA synthetic FHIR cohort",
                    [
                        sys.executable,
                        str(ROOT / "synthea/seed_tcga_cohort.py"),
                        "apply",
                        "--emit-baseline-telemetry",
                        "--resource-group",
                        cfg.get("resource_group_name", ""),
                        "--subscription",
                        cfg.get("expected_subscription_id", ""),
                    ],
                    root,
                )
                # HDS clinical ingestion reads NDJSON from the fhir-export container, not the FHIR API.
                await self.ps("rayfin-imaging: export TCGA FHIR cohort to ADLS", ROOT / "phase-1/deploy-fhir.ps1", {
                    "ResourceGroupName": cfg.get("resource_group_name", ""),
                    "ExpectedSubscriptionId": cfg.get("expected_subscription_id", ""),
                    "ExportOnly": True,
                    "ExportContainerName": "fhir-export",
                    "DeploymentPython": sys.executable,
                })
                await self.run_fabric_job(
                    "DataPipeline",
                    "healthcare1_msft_clinical_data_foundation_ingestion",
                    "Pipeline",
                    timeout_sec=3600,
                )
                await self.run_fabric_job(
                    "Notebook",
                    "materialize_reporting_tables",
                    "RunNotebook",
                    timeout_sec=3600,
                )
                await self.verify_silver_tcga_patients()
                await self.refresh_gold_sql_metadata()

            # 2. Researcher persona & de-identified clinical silo (ticket 006, opt-in only)
            researcher_flag = self.config.get("enable_researcher_persona", False)
            researcher_enabled = researcher_flag is True or (isinstance(researcher_flag, str) and researcher_flag.strip().lower() in ("true", "1", "yes"))
            if researcher_enabled:
                nurse_upn = str(cfg.get("researcher_persona_nurse_upn") or "").strip() or self._deployer_upn()
                persona_cmd = [
                    sys.executable,
                    str(ROOT / "scripts/manage_researcher_persona.py"),
                    "--create",
                    "--tenant-id", cfg["expected_tenant_id"],
                    "--workspace-id", self.ws,
                ]
                if nurse_upn:
                    persona_cmd.extend(["--nurse-upn", nurse_upn])
                await self.command("rayfin-imaging: manage researcher persona", persona_cmd)
                await self.command(
                    "rayfin-imaging: seed de-identified clinical silo",
                    [sys.executable, str(root / "pipeline/seed_deidentified_clinical.py"), "--live"],
                )

            # 3. SpO2 alert stopwatch & clinical activator (ticket 004, default True if alert_email set)
            alert_flag = self.config.get("enable_alert_stopwatch", True)
            alert_enabled = alert_flag is True or (isinstance(alert_flag, str) and alert_flag.strip().lower() in ("true", "1", "yes")) if alert_flag is not None else True
            alert_email = str(self.config.get("alert_email") or "").strip()
            if alert_enabled:
                if alert_email:
                    alert_env = {**self.env, "HLS_ALERT_EMAIL": alert_email}
                    await self.command(
                        "rayfin-imaging: deploy clinical activator reflex",
                        [sys.executable, str(ROOT / "scripts/deploy_clinical_activator.py"), "--live", "--workspace", cfg.get("fabric_workspace_name", "")],
                        root,
                        env=alert_env,
                    )
                    # The stopwatch is a live demo probe; an uncooperative Eventstream or Activator is logged
                    # and recorded on the add-on rather than aborting the Rayfin deployment.
                    try:
                        eh_ns = self.resource("Microsoft.EventHub/namespaces")["name"]
                        kql = self.item("KQLDatabase", "MasimoEventhouse")
                        kql_detail = await asyncio.to_thread(
                            self.cloud.call, "GET", f"{FABRIC}/v1/workspaces/{self.ws}/kqlDatabases/{kql['id']}", FABRIC, None, "eventhouse-cli",
                        )
                        eh_query_uri = ((kql_detail.get("properties") or {}).get("queryServiceUri") or "").strip()
                        if not eh_query_uri:
                            raise RuntimeError("MasimoEventhouse has no queryServiceUri")
                        await self.command(
                            "rayfin-imaging: trigger SpO2 alert stopwatch",
                            [
                                sys.executable,
                                str(ROOT / "scripts/trigger_spo2_alert.py"),
                                "--live",
                                "--workspace", cfg.get("fabric_workspace_name", ""),
                                "--eventhub-namespace", eh_ns,
                                "--resource-group", cfg.get("resource_group_name", ""),
                                "--eventhouse-query-uri", eh_query_uri,
                            ],
                            root,
                            env=alert_env,
                        )
                    except Exception as probe_exc:
                        warning = f"SpO2 alert stopwatch probe warning (non-fatal): {probe_exc}"
                        self.log(warning, "warn")
                        self.deployment.setdefault("customStatus", {}).setdefault("addons", {}).setdefault("rayfin", {}).setdefault("warnings", []).append(str(probe_exc))
                        self.persist()
                else:
                    self.substep("rayfin-imaging: deploy clinical activator reflex", "skipped", "skipped: no alert_email configured")
                    self.log("rayfin-imaging: alert stopwatch skipped: no alert_email configured", "info")
    async def cardiology(self, fresh_export=False):
        cfg = self.config
        wardflow = Path(os.environ.get("WARDFLOW_ROOT", str(Path.home() / "git/.worktrees/wardflow-jb-dev")))
        backend = wardflow / "caldova-cardio/hds-backend"
        if not backend.is_dir():
            raise RuntimeError("WARDFLOW_ROOT must contain the pinned jb-dev caldova-cardio/hds-backend")
        await asyncio.to_thread(ensure_providers_registered, cfg, CARDIOLOGY_PROVIDERS, True, 300)
        await self.ensure_eventstream_running("MasimoTelemetryStream")
        gold, sql = await self.gold()
        fhir = self.resource("Microsoft.HealthcareApis/workspaces/fhirservices")
        detail = await asyncio.to_thread(az_json, cfg, "resource", "show", "--ids", fhir["id"])
        fhir_url = detail["properties"]["authenticationConfiguration"]["audience"]
        parsed = urllib.parse.urlsplit(fhir_url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".fhir.azurehealthcareapis.com"):
            raise RuntimeError("Existing AHDS FHIR service endpoint is invalid")
        kql = self.item("KQLDatabase", "MasimoEventhouse")
        kql_detail = await asyncio.to_thread(self.cloud.call, "GET", f"{FABRIC}/v1/workspaces/{self.ws}/kqlDatabases/{kql['id']}", FABRIC, None, "eventhouse-cli")
        query_uri = kql_detail["properties"]["queryServiceUri"]
        pipeline = self.item("DataPipeline", "healthcare1_msft_clinical_data_foundation_ingestion")
        self.env.update(CARDIOLOGY_SUBSCRIPTION_ID=cfg["expected_subscription_id"], CARDIOLOGY_FHIR_URL=fhir_url,
                        CARDIOLOGY_FABRIC_WORKSPACE_ID=self.ws, CARDIOLOGY_INGEST_PIPELINE_ID=pipeline["id"],
                        CARDIOLOGY_SQL_HOST=sql["connectionString"], CARDIOLOGY_GOLD_SQL_ENDPOINT_ID=sql["id"])
        since = now()
        seed = backend / "cardiology-api/seed/seed_cardiology_cohort.py"
        await self.command("Cardiology cohort dry run", [sys.executable, seed])
        await self.command("Seed cardiology cohort", [sys.executable, seed, "--apply"])
        shared = {"ExpectedTenantId": cfg["expected_tenant_id"], "ExpectedSubscriptionId": cfg["expected_subscription_id"],
                  "FhirServiceId": fhir["id"], "FhirUrl": fhir_url, "EventhouseQueryUri": query_uri, "EventhouseDatabase": "MasimoEventhouse"}
        await self.ps("Deploy Masimo FHIR aggregator", backend / "phase-2/deploy-masimo-fhir-aggregator.ps1", {
            **shared, "ResourceGroupName": cfg["resource_group_name"], "EnvironmentName": "hds-dicom-env",
            "AcrName": self.resource("Microsoft.ContainerRegistry/registries")["name"]})
        await self.command("Deploy cardiology Gold projection", [sys.executable, backend / "cardiology-api/fabric/deploy_gold_projection.py",
                           "--subscription", cfg["expected_subscription_id"], "--workspace-id", self.ws])
        self.substep("Wait for HDS ingestion", "running")
        deadline = time.monotonic() + 7200
        while True:
            active = []
            for item in self.items:
                if item["type"] != "DataPipeline":
                    continue
                jobs = await asyncio.to_thread(self.cloud.items, f"{FABRIC}/v1/workspaces/{self.ws}/items/{item['id']}/jobs/instances", FABRIC, "spark-cli")
                active.extend(j for j in jobs if j.get("status") in {"NotStarted", "InProgress", "Running", "Queued"})
            if not active:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("HDS ingestion remained active for two hours; cardiology refresh was not started")
            if self.deployment.get("runtimeStatus") == "Terminated":
                raise RuntimeError("Cardiology add-on cancelled")
            await asyncio.sleep(30)
        self.substep("Wait for HDS ingestion", "succeeded")
        await self.command("Refresh cardiology Gold", [sys.executable, backend / "cardiology-api/fabric/refresh_cardiology_gold.py", "--since", since])
        prefix = cfg.get("cardiology_prefix") or "cardio" + re.sub("[^a-z0-9]", "", cfg["fabric_workspace_name"].lower())[-6:]
        group = f"rg-{cfg['fabric_workspace_name']}-cardio"
        rayfin_res = ((self.deployment.get("customStatus") or {}).get("addons") or {}).get("rayfin", {}).get("resources") or {}
        await self.ps("Deploy cardiology app", backend / "phase-8/deploy-cardiology-app.ps1", {
            **shared, "ResourceGroupName": group, "Location": cfg["cardiology_location"], "Prefix": prefix,
            "Tags": {**cfg.get("tags", {}), "hls-deployment": cfg["fabric_workspace_name"]},
            "FabricWorkspaceId": self.ws, "FabricSqlHost": sql["connectionString"], "FabricGoldDatabase": gold["displayName"],
            "CardiologyAppPath": str(wardflow / "caldova-cardio/app"), "CardiologyAppUsers": cfg["cardiology_app_users"],
            "CardiologyReviewerUsers": cfg["cardiology_reviewer_users"], "ChatModelName": cfg["cardiology_chat_model"],
            "ChatModelVersion": cfg["cardiology_chat_model_version"],
            **({"RayfinImagingUrl": rayfin_res["rayfin-imaging"]} if rayfin_res.get("rayfin-imaging") else {}),
            **({"RayfinCommandCenterUrl": rayfin_res["rayfin-health-command-center"]} if rayfin_res.get("rayfin-health-command-center") else {}),
            **({"RayfinClinicalTriageUrl": rayfin_res["rayfin-clinical-triage-app"]} if rayfin_res.get("rayfin-clinical-triage-app") else {})})
        app = await asyncio.to_thread(az_json, cfg, "containerapp", "show", "-g", group, "-n", prefix + "-app")
        return {"resourceGroup": group, "url": "https://" + app["properties"]["configuration"]["ingress"]["fqdn"]}
