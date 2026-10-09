"""Subscription-pinned add-ons over a completed HLS estate; no interactive login."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from shared.full_teardown import AzureCliTokens, ARM, FABRIC, GRAPH, DATABRICKS
from shared.runtime_paths import DATA_DIR

ROOT = Path(__file__).resolve().parents[2]
ADDON_FLAGS = {"databricks": "deploy_databricks", "rayfin": "deploy_rayfin_apps", "cardiology": "deploy_cardiology"}
MODEL_CANDIDATES = [("gpt-5.6-luna", "2026-07-09"), ("gpt-5.5", "2026-04-24")]
CONTINUATIONS: dict[str, asyncio.Event] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def selected(config: dict) -> list[str]:
    return [name for name, flag in ADDON_FLAGS.items() if config.get(flag)]


def az_json(config: dict, *args: str):
    result = subprocess.run(["az", *args, "--subscription", config["expected_subscription_id"], "-o", "json"],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:1000] or "Azure CLI command failed")
    return json.loads(result.stdout or "null")


class Cloud:
    def __init__(self, config: dict):
        self.tokens = AzureCliTokens(config["expected_subscription_id"])
        self.expected_tenant = config["expected_tenant_id"]

    def call(self, method: str, url: str, resource: str = FABRIC, body=None, skill="search-consumption-cli"):
        token = self.tokens.token(resource)
        if self.tokens.tenant_id != self.expected_tenant:
            raise RuntimeError("Add-on token tenant differs from the deployment tenant")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if urllib.parse.urlsplit(url).hostname == "api.fabric.microsoft.com":
            headers["x-ms-fabric-skill"] = skill
        req = urllib.request.Request(url, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def items(self, url: str, resource=FABRIC, skill="search-consumption-cli") -> list[dict]:
        values = []
        origin = urllib.parse.urlsplit(url).netloc
        while url:
            body = self.call("GET", url, resource, skill=skill)
            values.extend(body.get("value", []))
            url = body.get("continuationUri") or body.get("nextLink") or body.get("@odata.nextLink")
            if url and urllib.parse.urlsplit(url).netloc != origin:
                raise RuntimeError("Cross-origin API continuation refused")
        return values


def preflight(config: dict) -> list[dict]:
    checks = []

    def check(name, action):
        try:
            detail = action()
            checks.append({"name": name, "status": "pass", "message": detail, "detail": detail})
        except Exception as exc:
            checks.append({"name": name, "status": "fail", "message": str(exc), "detail": str(exc)})

    if config.get("deploy_databricks"):
        def databricks():
            provider = az_json(config, "provider", "show", "--namespace", "Microsoft.Databricks")
            if provider.get("registrationState") != "Registered":
                raise RuntimeError("Register Microsoft.Databricks in the deployment subscription first")
            locations = Cloud(config).call("GET", f"{ARM}/subscriptions/{config['expected_subscription_id']}/locations?api-version=2022-12-01", ARM)["value"]
            region = next((x for x in locations if x["name"] == config["location"]), None)
            available = next((x.get("locations", []) for x in provider.get("resourceTypes", []) if x["resourceType"].lower() == "workspaces"), [])
            if not region or region["displayName"] not in available:
                raise RuntimeError(f"Databricks workspaces are not offered in {config['location']}")
            missing = [x for x in ("azcopy", "databricks", "jq", "bash") if not shutil.which(x)]
            if missing:
                raise RuntimeError("Missing add-on tools: " + ", ".join(missing))
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
            location = config["cardiology_location"]
            offered = az_json(config, "cognitiveservices", "model", "list", "-l", location)
            usage = az_json(config, "cognitiveservices", "usage", "list", "-l", location)
            candidates = [(config["cardiology_chat_model"], config["cardiology_chat_model_version"])] if config.get("cardiology_chat_model") else MODEL_CANDIDATES
            for name, version in candidates:
                available = any(m.get("model", {}).get("name") == name and m["model"].get("version") == version and
                                any(s.get("name") == "DataZoneStandard" for s in m["model"].get("skus", [])) for m in offered)
                quota = next((q for q in usage if q.get("name", {}).get("value") == f"OpenAI.DataZoneStandard.{name}"), {})
                free = float(quota.get("limit", 0)) - float(quota.get("currentValue", 0))
                if available and free >= 50:
                    return f"{name} {version}: DataZoneStandard in {location}, {free:g}K TPM free"
            raise RuntimeError(f"No requested model/version offered as DataZoneStandard with >=50K TPM free in {location}")
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


class AddonRunner:
    def __init__(self, instance_id, config, deployment, save, pids):
        self.id, self.config, self.deployment = instance_id, config, deployment
        self.save, self.pids = save, pids
        self.cloud = Cloud(config)
        self.work = DATA_DIR / "addons" / instance_id
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

    async def command(self, title, args, cwd=None, env=None, capture=False, input_text=None):
        if self.deployment.get("runtimeStatus") == "Terminated":
            raise RuntimeError("Add-on cancelled")
        self.substep(title, "running")
        self.log(title)
        process = await asyncio.create_subprocess_exec(*map(str, args), cwd=str(cwd or ROOT), env=env or self.env,
            stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE if capture else asyncio.subprocess.STDOUT,
            start_new_session=True)
        self.pids[self.id] = process.pid
        try:
            if capture:
                output, errors = await process.communicate(input_text.encode() if input_text is not None else None)
                text = output.decode(errors="replace")
                if process.returncode:
                    raise RuntimeError(f"{title}: {errors.decode(errors='replace')[:1500]}")
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
                    raise RuntimeError(f"{title} exited with code {process.returncode}")
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

    async def gold(self):
        gold = self.item("Lakehouse", "healthcare1_reporting_gold")
        detail = await asyncio.to_thread(self.cloud.call, "GET", f"{FABRIC}/v1/workspaces/{self.ws}/lakehouses/{gold['id']}")
        sql = detail["properties"]["sqlEndpointProperties"]
        if not sql.get("connectionString") or not sql.get("id"):
            raise RuntimeError("Gold SQL endpoint is not provisioned")
        return gold, sql

    async def run(self, addons, fresh_export=False):
        cs = self.deployment["customStatus"]
        await self.discover()
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
                raise
            finally:
                self.persist()

    def working_copy(self, source, name):
        target = self.work / name
        if not target.exists():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("node_modules", "dist", ".git", ".env*", ".state", ".databricks", ".deployments.json", "*.tsbuildinfo", ".temp"))
        return target

    async def databricks(self, fresh_export=False):
        import yaml
        cfg = self.config
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
        group_info = await asyncio.to_thread(az_json, cfg, "ad", "group", "show", "--group", group)
        account = await asyncio.to_thread(az_json, cfg, "account", "show")
        variables = {
            "AZ_TENANT_ID": cfg["expected_tenant_id"], "AZ_SUBSCRIPTION_ID": cfg["expected_subscription_id"],
            "AZ_RESOURCE_GROUP": cfg["resource_group_name"], "AZ_LOCATION": cfg["location"],
            "ADMIN_GROUP_OBJECT_ID": group_info["id"], "DATABRICKS_ADMIN_GROUP": group_info["displayName"],
            "STORAGE_ACCOUNT_NAME": storage, "EVENTHUB_NAMESPACE": self.resource("Microsoft.EventHub/namespaces")["name"],
            "KEY_VAULT_NAME": self.resource("Microsoft.KeyVault/vaults")["name"],
            "TELEMETRY_HUB": "telemetry-stream", "CLAIMS_HUB": "claim-stream",
            "TELEMETRY_CONSUMER_GROUP": "hls-dbx-telemetry", "CLAIMS_CONSUMER_GROUP": "hls-dbx-claims",
            "DATABRICKS_LISTEN_POLICY": "hls-databricks-listen", "EVENTHUB_SECRET_SCOPE": "hls-eventhubs", "EVENTHUB_SECRET_KEY": "listen-key",
            "ENVIRONMENT": cfg["databricks_environment"], "DATABRICKS_AUTH_TYPE": "azure-cli", "HLS_NONINTERACTIVE": "1",
            "FHIR_EXPORT_CONTAINER": "fhir-export-databricks", "FHIR_EXPORT_URL": f"abfss://fhir-export-databricks@{storage}.dfs.core.windows.net",
            "WORKLOAD_PRINCIPAL": account["user"]["name"], "ALERT_EMAIL": cfg.get("alert_email", "")}
        # Hosted jobs use the authenticated deployer, not an unrelated service principal.
        bundle_path = root / "bundle/databricks.yml"
        bundle = yaml.safe_load(bundle_path.read_text())
        for target in bundle["targets"].values():
            target.pop("run_as", None)
        bundle_path.write_text(yaml.safe_dump(bundle, sort_keys=False))
        def save_env():
            path = root / "env.sh"
            path.write_text("\n".join(f"export {key}={shlex.quote(str(value))}" for key, value in variables.items()) + "\n")
            path.chmod(0o600)
        save_env()
        env = {**self.env, **variables}
        scripts = root / "scripts"
        for step in ("01-preflight.sh", "02-deploy-databricks-foundation.sh"):
            await self.command(step, ["bash", scripts / step], root, env)
        foundation = json.loads((root / f".state/foundation-{variables['ENVIRONMENT']}.json").read_text())
        for key, output in (("DATABRICKS_HOST", "workspaceUrl"), ("ACCESS_CONNECTOR_ID", "accessConnectorId"),
                            ("MANAGED_LOCATION_URL", "managedLocationUrl"), ("DICOM_OUTPUT_URL", "dicomOutputUrl")):
            variables[key] = foundation[output]["value"]
        env.update(variables)
        save_env()
        await self.ensure_metastore(env, root)
        for step in ("03-configure-eventhubs-access.sh", "04-unity-catalog-bootstrap.sh", "05-deploy-bundle.sh", "06-run-and-gate.sh"):
            await self.command(step, ["bash", scripts / step], root, env)
            if step == "04-unity-catalog-bootstrap.sh":
                env["WAREHOUSE_ID"] = json.loads((root / f".state/warehouse-{variables['ENVIRONMENT']}.json").read_text())["warehouse_id"]
        await self.command("07 Databricks deployment validation", [sys.executable, scripts / "07-validate-deployment.py", "--environment", variables["ENVIRONMENT"]], root, env)
        return {"workspaceUrl": variables["DATABRICKS_HOST"], "fhirExportUrl": variables["FHIR_EXPORT_URL"]}

    async def ensure_metastore(self, env, root):
        async def assigned():
            try:
                result = json.loads(await self.command("Check Unity Catalog metastore", ["databricks", "metastores", "current", "-o", "json"], root, env, capture=True))
                return bool(result.get("metastore_id"))
            except RuntimeError:
                return False
        if await assigned():
            return
        explanation = ""
        try:
            endpoint = "https://accounts.azuredatabricks.net/api/2.0"
            accounts = await asyncio.to_thread(self.cloud.call, "GET", endpoint + "/accounts", DATABRICKS)
            candidates = accounts if isinstance(accounts, list) else accounts.get("accounts", [])
            matches = []
            for account in candidates:
                account_id = account.get("account_id") or account.get("id")
                data = await asyncio.to_thread(self.cloud.call, "GET", f"{endpoint}/accounts/{account_id}/metastores", DATABRICKS)
                for metastore in data.get("metastores", []):
                    if metastore.get("region", "").replace(" ", "").lower() == self.config["location"].lower():
                        matches.append((account_id, metastore["metastore_id"]))
            account_id, metastore_id = require_one(matches, "regional Databricks account metastore")
            dbx = self.resource("Microsoft.Databricks/workspaces") if any(r["type"].lower() == "microsoft.databricks/workspaces" for r in self.azure) else require_one(await asyncio.to_thread(az_json, self.config, "databricks", "workspace", "list", "-g", self.config["resource_group_name"]), "Databricks workspace")
            workspace_id = dbx.get("workspaceId") or dbx.get("properties", {}).get("workspaceId")
            if not workspace_id:
                detail = await asyncio.to_thread(az_json, self.config, "databricks", "workspace", "show", "--ids", dbx["id"])
                workspace_id = detail["workspaceId"]
            await asyncio.to_thread(self.cloud.call, "PUT", f"{endpoint}/accounts/{account_id}/workspaces/{workspace_id}/metastore", DATABRICKS,
                                    {"metastore_id": metastore_id, "default_catalog_name": "hive_metastore"})
            if await assigned():
                return
            explanation = "Assignment is not yet visible."
        except (urllib.error.HTTPError, RuntimeError, KeyError) as exc:
            explanation = f"Automatic metastore assignment unavailable: {exc}."
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
                    if self.deployment.get("runtimeStatus") == "Terminated":
                        raise RuntimeError("Add-on cancelled while awaiting metastore assignment")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("Databricks metastore assignment timed out after 24 hours")
                    try:
                        await asyncio.wait_for(event.wait(), timeout=min(remaining, 30))
                    except asyncio.TimeoutError:
                        pass
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
        for app in ("rayfin-health-command-center", "rayfin-clinical-triage-app"):
            root = self.working_copy(ROOT / app, app)
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
            await self.command(f"{app}: provision backend", up + ["--exclude-services", "staticHosting,functions"], root, await rayfin_env())
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
            await self.command(f"{app}: build", ["npm", "run", "build"], root, await rayfin_env("https://analysis.windows.net/powerbi/api"))
            await self.command(f"{app}: deploy", up, root, await rayfin_env())
            status = json.loads(await self.command(f"{app}: hosting details", cli + ["up", "status", "--json"], root, await rayfin_env(), capture=True))
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
            await self.command(f"{app}: register hosting origin", up + ["--exclude-services", "staticHosting,functions"], root, await rayfin_env())
            result[app] = hosting
        return result

    async def cardiology(self, fresh_export=False):
        cfg = self.config
        wardflow = Path(os.environ.get("WARDFLOW_ROOT", str(Path.home() / "git/.worktrees/wardflow-jb-dev")))
        backend = wardflow / "caldova-cardio/hds-backend"
        if not backend.is_dir():
            raise RuntimeError("WARDFLOW_ROOT must contain the pinned jb-dev caldova-cardio/hds-backend")
        gold, sql = await self.gold()
        fhir = self.resource("Microsoft.HealthcareApis/workspaces/fhirservices")
        detail = await asyncio.to_thread(az_json, cfg, "resource", "show", "--ids", fhir["id"])
        fhir_url = detail["properties"]["hostName"]
        if not fhir_url.startswith("https://"):
            fhir_url = "https://" + fhir_url
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
        prefix = cfg.get("cardiology_prefix") or "cardio" + re.sub("[^a-z0-9]", "", cfg["fabric_workspace_name"].lower())[-12:]
        group = f"rg-{cfg['fabric_workspace_name']}-cardio"
        await self.ps("Deploy cardiology app", backend / "phase-8/deploy-cardiology-app.ps1", {
            **shared, "ResourceGroupName": group, "Location": cfg["cardiology_location"], "Prefix": prefix,
            "Tags": {**cfg.get("tags", {}), "hls-deployment": cfg["fabric_workspace_name"]},
            "FabricWorkspaceId": self.ws, "FabricSqlHost": sql["connectionString"], "FabricGoldDatabase": gold["displayName"],
            "CardiologyAppPath": str(wardflow / "caldova-cardio/app"), "CardiologyAppUsers": cfg["cardiology_app_users"],
            "CardiologyReviewerUsers": cfg["cardiology_reviewer_users"], "ChatModelName": cfg["cardiology_chat_model"],
            "ChatModelVersion": cfg["cardiology_chat_model_version"]})
        app = await asyncio.to_thread(az_json, cfg, "containerapp", "show", "-g", group, "-n", prefix + "-app")
        return {"resourceGroup": group, "url": "https://" + app["properties"]["configuration"]["ingress"]["fqdn"]}
