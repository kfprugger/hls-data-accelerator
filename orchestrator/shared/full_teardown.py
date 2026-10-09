"""Ownership-aware teardown of one HLS deployment and every front end tied to it.

Shared by the local and hosted orchestrator API and ``Teardown-All.ps1``
(``python -m shared.full_teardown``). Every Azure, Graph, Fabric and Databricks token is minted for
one explicit subscription and checked against the expected tenant before anything is deleted, so an
Azure CLI default that points at another tenant can never become the target.

Order: preflight and plan, Rayfin front ends, Databricks Unity Catalog objects, Fabric connections,
workspace identity, workspace, front-end Entra apps, front-end resource groups, main resource
group, final read-back verification. Front-end resource groups come from explicit input and from
discovery; a resource group is only deleted when it is tied to this deployment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterator, Protocol

ARM = "https://management.azure.com"
GRAPH = "https://graph.microsoft.com"
FABRIC = "https://api.fabric.microsoft.com"
DATABRICKS = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"  # Azure Databricks first-party application
FABRIC_SKILL = "onelake-catalog-govern-cli"
DEPLOYMENT_TAG = "hls-deployment"
CARDIOLOGY_OWNER_TAG = "hls-cardiology-app:"

PHASE_PREFLIGHT = "Preflight"
PHASE_FRONT_END_APPS = "Front-End Apps"
PHASE_DATABRICKS = "Databricks Unity Catalog"
PHASE_CONNECTIONS = "Fabric Connections"
PHASE_IDENTITY = "Workspace Identity"
PHASE_WORKSPACE = "Delete Workspace"
PHASE_FRONT_END_IDENTITIES = "Front-End Entra Apps"
PHASE_FRONT_END_GROUPS = "Front-End Resource Groups"
PHASE_MAIN_GROUP = "Azure Resource Group"
PHASE_VERIFY = "Verification"

# Resource types a front-end stack consists of; any other type makes a discovered group "shared".
FRONT_END_TYPES = {
    "microsoft.app/containerapps", "microsoft.app/jobs", "microsoft.app/managedenvironments",
    "microsoft.containerregistry/registries", "microsoft.managedidentity/userassignedidentities",
    "microsoft.storage/storageaccounts", "microsoft.documentdb/databaseaccounts",
    "microsoft.cognitiveservices/accounts", "microsoft.insights/components",
    "microsoft.operationalinsights/workspaces", "microsoft.eventhub/namespaces",
    "microsoft.eventgrid/systemtopics", "microsoft.web/staticsites", "microsoft.web/sites",
    "microsoft.web/serverfarms", "microsoft.keyvault/vaults", "microsoft.insights/actiongroups",
    "microsoft.alertsmanagement/smartdetectoralertrules",
}
COMPUTE_TYPES = {"microsoft.app/containerapps", "microsoft.app/jobs"}
PROTECTED_TYPES = {"microsoft.fabric/capacities"}
FRONT_END_ITEM_TYPES = ("UserDataFunction", "SQLDatabase")  # Rayfin companions named after the AppBackend


class TeardownRefused(Exception):
    """The request is unsafe or invalid; nothing was deleted."""


class Report(Protocol):
    def log(self, level: str, message: str) -> None: ...
    def phase(self, name: str, status: str) -> None: ...


@dataclass
class TeardownSpec:
    workspace_name: str = ""
    resource_group_name: str = ""
    delete_workspace: bool = False
    delete_azure_rg: bool = True
    subscription_id: str = ""
    expected_tenant_id: str = ""
    front_end_resource_groups: list[str] = field(default_factory=list)
    discover_front_ends: bool = True
    wait_minutes: int = 45


@dataclass
class FrontEndGroup:
    name: str
    explicit: bool
    ties: list[str]
    kind: str = "front end"
    delete: bool = False
    skip_reason: str = ""


@dataclass
class TeardownPlan:
    tenant_id: str
    subscription_id: str
    workspace_id: str = ""
    app_backends: list[dict] = field(default_factory=list)
    companion_items: list[dict] = field(default_factory=list)
    main_group_exists: bool = False
    tie_values: list[str] = field(default_factory=list)
    connector_ids: list[str] = field(default_factory=list)
    databricks_urls: list[str] = field(default_factory=list)
    front_ends: list[FrontEndGroup] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- tokens


class TokenProvider(Protocol):
    tenant_id: str

    def token(self, resource: str) -> str: ...


class AzureCliTokens:
    """Tokens from ``az account get-access-token --subscription``: never the CLI default account."""

    def __init__(self, subscription_id: str, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
        if not subscription_id:
            raise TeardownRefused("subscription_id is required; the Azure CLI default subscription is never used")
        self.subscription_id = subscription_id
        self.tenant_id = ""
        self._runner = runner
        self._cache: dict[str, tuple[str, float]] = {}

    def token(self, resource: str) -> str:
        cached = self._cache.get(resource)
        if cached and cached[1] - 300 > time.time():
            return cached[0]
        args = ["az", "account", "get-access-token", "--subscription", self.subscription_id,
                "--resource", resource, "-o", "json"]
        proc = self._runner(args, capture_output=True, text=True, shell=sys.platform == "win32")
        if proc.returncode != 0:
            raise TeardownRefused(f"cannot get a {resource} token for subscription {self.subscription_id}: "
                                  f"{(proc.stderr or '').strip()[:300]}")
        data = json.loads(proc.stdout)
        tenant = data.get("tenant", "")
        if self.tenant_id and tenant != self.tenant_id:
            raise TeardownRefused(f"token tenants disagree ({self.tenant_id} vs {tenant})")
        self.tenant_id = tenant
        expires = float(data.get("expires_on") or time.time() + 1800)
        self._cache[resource] = (data["accessToken"], expires)
        return data["accessToken"]




# --------------------------------------------------------------------------- HTTP


class HttpError(Exception):
    def __init__(self, status: int, method: str, url: str, body: str) -> None:
        super().__init__(f"{method} {url.split('?')[0]} -> HTTP {status}: {body[:300]}")
        self.status = status


Opener = Callable[[urllib.request.Request, float], Any]


class Rest:
    def __init__(self, tokens: TokenProvider, opener: Opener | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.tokens = tokens
        self._open = opener or (lambda request, timeout: urllib.request.urlopen(request, timeout=timeout))
        self._sleep = sleep

    def call(self, method: str, url: str, resource: str, body: Any = None) -> tuple[int, Any]:
        headers = {"Authorization": f"Bearer {self.tokens.token(resource)}", "Content-Type": "application/json"}
        if urllib.parse.urlparse(url).hostname == "api.fabric.microsoft.com":
            headers["x-ms-fabric-skill"] = FABRIC_SKILL
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(6):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with self._open(request, 60) as response:
                    raw = response.read().decode() if response.status != 204 else ""
                    return response.status, json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as error:
                text = error.read().decode(errors="replace")
                if error.code in (429, 503) and attempt < 5:
                    self._sleep(float(error.headers.get("Retry-After") or 10))
                    continue
                if error.code == 404:
                    return 404, None
                raise HttpError(error.code, method, url, text) from None
        raise HttpError(429, method, url, "throttled")

    def pages(self, url: str, resource: str, key: str = "value") -> Iterator[dict]:
        while url:
            status, body = self.call("GET", url, resource)
            if status == 404 or not body:
                return
            yield from body.get(key) or []
            url = body.get("nextLink") or body.get("continuationUri") or body.get("@odata.nextLink") or ""


# --------------------------------------------------------------------------- teardown


def _host(value: str) -> str:
    parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower()


def _resource_group_of(resource_id: str) -> str:
    parts = resource_id.split("/")
    lowered = [p.lower() for p in parts]
    return parts[lowered.index("resourcegroups") + 1] if "resourcegroups" in lowered else ""


class DeploymentTeardown:
    def __init__(self, spec: TeardownSpec, tokens: TokenProvider, report: Report, rest: Rest | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.spec = spec
        self.tokens = tokens
        self.report = report
        self.rest = rest or Rest(tokens)
        self._sleep = sleep
        self.failures: list[str] = []
        self.deleted: dict[str, list[str]] = {}

    # ---------------------------------------------------------------- helpers

    def _arm(self, path: str) -> str:
        return f"{ARM}/subscriptions/{self.spec.subscription_id}{path}"

    def _record(self, kind: str, name: str) -> None:
        self.deleted.setdefault(kind, []).append(name)

    def _fail(self, message: str) -> None:
        self.failures.append(message)
        self.report.log("error", message)

    def _group_resources(self, group: str) -> list[dict] | None:
        status, _ = self.rest.call("GET", self._arm(f"/resourcegroups/{group}?api-version=2021-04-01"), ARM)
        if status == 404:
            return None
        return list(self.rest.pages(self._arm(f"/resourceGroups/{group}/resources?api-version=2021-04-01"), ARM))

    def _graph_query(self, query: str) -> list[dict]:
        rows: list[dict] = []
        body: dict[str, Any] = {"subscriptions": [self.spec.subscription_id], "query": query,
                                "options": {"resultFormat": "objectArray", "$top": 1000}}
        while True:
            _, result = self.rest.call("POST", f"{ARM}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01", ARM, body)
            rows.extend((result or {}).get("data") or [])
            token = (result or {}).get("$skipToken")
            if not token:
                return rows
            body["options"]["$skipToken"] = token

    # ---------------------------------------------------------------- plan

    def preflight(self) -> TeardownPlan:
        spec = self.spec
        if not (spec.workspace_name or spec.resource_group_name):
            raise TeardownRefused("nothing to tear down: set a workspace and/or a resource group")
        if not spec.subscription_id:
            raise TeardownRefused("subscription_id is required; the Azure CLI default subscription is never used")
        self.tokens.token(ARM)
        tenant = self.tokens.tenant_id
        if spec.expected_tenant_id and tenant.lower() != spec.expected_tenant_id.lower():
            raise TeardownRefused(f"subscription {spec.subscription_id} resolves to tenant {tenant}, not the expected "
                                  f"{spec.expected_tenant_id}; refusing to delete anything")
        status, subscription = self.rest.call("GET", self._arm("?api-version=2022-12-01"), ARM)
        if status == 404 or (subscription or {}).get("tenantId", "").lower() != tenant.lower():
            raise TeardownRefused(f"subscription {spec.subscription_id} is not visible in tenant {tenant}")
        plan = TeardownPlan(tenant_id=tenant, subscription_id=spec.subscription_id)
        self.report.log("info", f"Pinned to subscription {spec.subscription_id} in tenant {tenant}")
        ties: set[str] = set()
        if spec.workspace_name:
            self._plan_workspace(plan, ties)
        if spec.resource_group_name:
            self._plan_main_group(plan, ties)
        plan.tie_values = sorted(ties)
        self._plan_front_ends(plan)
        return plan

    def _plan_workspace(self, plan: TeardownPlan, ties: set[str]) -> None:
        match = [w for w in self.rest.pages(f"{FABRIC}/v1/workspaces", FABRIC) if w.get("displayName") == self.spec.workspace_name]
        if not match:
            self.report.log("warn", f"Fabric workspace '{self.spec.workspace_name}' not found")
            return
        plan.workspace_id = match[0]["id"]
        ties.add(plan.workspace_id.lower())
        items = list(self.rest.pages(f"{FABRIC}/v1/workspaces/{plan.workspace_id}/items", FABRIC))
        plan.app_backends = [{"id": i["id"], "name": i["displayName"]} for i in items if i.get("type") == "AppBackend"]
        names = {b["name"] for b in plan.app_backends}
        plan.companion_items = [{"id": i["id"], "name": i["displayName"], "type": i["type"]} for i in items
                                if i.get("type") in FRONT_END_ITEM_TYPES and i.get("displayName") in names]
        unavailable: set[str] = set()
        for kind, prop in (("lakehouses", ("sqlEndpointProperties", "connectionString")),
                           ("warehouses", ("connectionString",)), ("eventhouses", ("queryServiceUri",)),
                           ("eventhouses", ("ingestionServiceUri",))):
            status, body = self.rest.call("GET", f"{FABRIC}/v1/workspaces/{plan.workspace_id}/{kind}", FABRIC)
            if status == 404:  # these listings need an active capacity
                unavailable.add(kind)
                continue
            for item in (body or {}).get("value") or []:
                value: Any = item.get("properties") or {}
                for key in prop:
                    value = (value or {}).get(key) if isinstance(value, dict) else None
                if isinstance(value, str) and value:
                    ties.add(_host(value))
        if unavailable:
            self.report.log("warn", f"Could not read {', '.join(sorted(unavailable))} endpoints (is the capacity paused?): "
                                    "a front end tied only to the SQL endpoint or Eventhouse will not be discovered; "
                                    "pass its resource group explicitly")
        self.report.log("info", f"Workspace {plan.workspace_id}: {len(items)} items, "
                                f"{len(plan.app_backends)} Rayfin app(s)")

    def _plan_main_group(self, plan: TeardownPlan, ties: set[str]) -> None:
        resources = self._group_resources(self.spec.resource_group_name)
        if resources is None:
            self.report.log("warn", f"Resource group '{self.spec.resource_group_name}' not found")
            return
        plan.main_group_exists = True
        for resource in resources:
            kind, name, rid = resource["type"].lower(), resource["name"], resource["id"]
            if kind == "microsoft.healthcareapis/workspaces/fhirservices":
                _, body = self.rest.call("GET", f"{ARM}{rid}?api-version=2023-11-01", ARM)
                audience = ((body or {}).get("properties") or {}).get("authenticationConfiguration", {}).get("audience", "")
                if audience:
                    ties.add(_host(audience))
            elif kind == "microsoft.storage/storageaccounts":
                ties.update(f"{name}.{svc}.core.windows.net".lower() for svc in ("blob", "dfs", "queue", "table", "file"))
            elif kind == "microsoft.eventhub/namespaces":
                ties.add(f"{name}.servicebus.windows.net".lower())
            elif kind == "microsoft.databricks/accessconnectors":
                plan.connector_ids.append(rid.lower())
            elif kind == "microsoft.databricks/workspaces":
                _, body = self.rest.call("GET", f"{ARM}{rid}?api-version=2024-05-01", ARM)
                url = ((body or {}).get("properties") or {}).get("workspaceUrl", "")
                if url:
                    plan.databricks_urls.append(url)
        self.report.log("info", f"Resource group '{self.spec.resource_group_name}': {len(resources)} resources")

    def _ties_in(self, resource: dict, ties: list[str]) -> list[str]:
        found: set[str] = set()
        for container in resource.get("containers") or []:
            for env in (container or {}).get("env") or []:
                value = str((env or {}).get("value") or "").lower()
                found.update(t for t in ties if t and t in value)
        return sorted(found)

    def _plan_front_ends(self, plan: TeardownPlan) -> None:
        spec = self.spec
        main = spec.resource_group_name.lower()
        tied_groups: dict[str, set[str]] = {}
        tied_apps: set[str] = set()
        if plan.tie_values:
            apps = self._graph_query("resources | where type in~ ('microsoft.app/containerapps', 'microsoft.app/jobs') "
                                     "| project id, name, resourceGroup, containers = properties.template.containers")
            for app in apps:
                found = self._ties_in(app, plan.tie_values)
                if found:
                    tied_apps.add(app["id"].lower())
                    tied_groups.setdefault(app["resourceGroup"].lower(), set()).add(f"{app['name']} -> {', '.join(found)}")
        names = [n for n in (spec.workspace_name, spec.resource_group_name) if n]
        if names:
            values = ", ".join("'" + n.replace("'", "''") + "'" for n in names)
            tagged = self._graph_query(
                "resourcecontainers | where type =~ 'microsoft.resources/subscriptions/resourcegroups' "
                f"| where tostring(tags['{DEPLOYMENT_TAG}']) in~ ({values}) | project name")
            for group in tagged:
                tied_groups.setdefault(group["name"].lower(), set()).add(f"tag {DEPLOYMENT_TAG}")
        candidates = {g: True for g in (n.lower() for n in spec.front_end_resource_groups) if g and g != main}
        if spec.discover_front_ends:
            for group in tied_groups:
                candidates.setdefault(group, False)
        candidates.pop(main, None)
        for group, explicit in sorted(candidates.items()):
            plan.front_ends.append(self._judge_group(group, explicit, sorted(tied_groups.get(group, ())), tied_apps))
        for front_end in plan.front_ends:
            verdict = "delete" if front_end.delete else f"keep ({front_end.skip_reason})"
            self.report.log("info", f"Front end '{front_end.name}' [{front_end.kind}, "
                                    f"{'explicit' if front_end.explicit else 'discovered'}]: {verdict}")

    def _judge_group(self, group: str, explicit: bool, ties: list[str], tied_apps: set[str]) -> FrontEndGroup:
        front_end = FrontEndGroup(name=group, explicit=explicit, ties=ties)
        resources = self._group_resources(group)
        if resources is None:
            front_end.skip_reason = "resource group not found"
            return front_end
        kinds = {r["type"].lower() for r in resources}
        if kinds & PROTECTED_TYPES:
            raise TeardownRefused(f"resource group '{group}' contains a Fabric capacity; it is never deleted by teardown")
        tagged = any(t.startswith("tag ") for t in ties)
        if explicit:
            if not ties:
                raise TeardownRefused(f"explicit front-end resource group '{group}' has nothing tied to this deployment "
                                      "(no app referencing its FHIR, Fabric, Event Hubs or storage endpoints and no "
                                      f"'{DEPLOYMENT_TAG}' tag); refusing")
            front_end.delete = True
            return front_end
        stray = sorted(r["name"] for r in resources if r["type"].lower() not in FRONT_END_TYPES
                       or (r["type"].lower() in COMPUTE_TYPES and r["id"].lower() not in tied_apps and not tagged))
        if stray:
            front_end.skip_reason = (f"shared resource group: {', '.join(stray[:5])} not part of this deployment's front end; "
                                     "pass it explicitly to delete it")
            return front_end
        front_end.delete = True
        return front_end

    # ---------------------------------------------------------------- execute

    def run(self, plan_only: bool = False) -> dict[str, Any]:
        self.report.phase(PHASE_PREFLIGHT, "running")
        try:
            plan = self.preflight()
        except TeardownRefused as refused:
            self.report.log("error", f"Refused: {refused}")
            self.report.phase(PHASE_PREFLIGHT, "failed")
            raise
        self.report.phase(PHASE_PREFLIGHT, "succeeded")
        result: dict[str, Any] = {"plan": plan.summary(), "planOnly": plan_only}
        if plan_only:
            return result
        spec = self.spec
        if spec.delete_workspace and plan.workspace_id:
            self._step(PHASE_FRONT_END_APPS, self._delete_front_end_apps, plan)
        if spec.delete_azure_rg and plan.databricks_urls:
            self._step(PHASE_DATABRICKS, self._delete_unity_catalog, plan)
        if (spec.delete_workspace or spec.delete_azure_rg) and plan.tie_values:
            self._step(PHASE_CONNECTIONS, self._delete_connections, plan)
        if spec.delete_workspace and plan.workspace_id:
            self._step(PHASE_IDENTITY, self._delete_workspace_identity, plan)
            self._step(PHASE_WORKSPACE, self._delete_workspace, plan)
        groups = [f for f in plan.front_ends if f.delete]
        if groups:
            self._step(PHASE_FRONT_END_IDENTITIES, self._delete_front_end_identities, plan)
            self._step(PHASE_FRONT_END_GROUPS, lambda p: self._delete_groups([f.name for f in groups]), plan)
        if spec.delete_azure_rg and plan.main_group_exists:
            self._step(PHASE_MAIN_GROUP, lambda p: self._delete_groups([spec.resource_group_name]), plan)
        self._step(PHASE_VERIFY, self._verify, plan)
        result.update({"deleted": self.deleted, "failures": self.failures,
                       "skipped": [asdict(f) for f in plan.front_ends if not f.delete],
                       "status": "failed" if self.failures else "succeeded"})
        return result

    def _step(self, name: str, action: Callable[[TeardownPlan], None], plan: TeardownPlan) -> None:
        before = len(self.failures)
        self.report.phase(name, "running")
        try:
            action(plan)
        except Exception as error:  # one phase failing must not hide the others
            self._fail(f"{name}: {error}")
        self.report.phase(name, "failed" if len(self.failures) > before else "succeeded")

    def _delete_item(self, plan: TeardownPlan, item: dict, label: str) -> None:
        url = f"{FABRIC}/v1/workspaces/{plan.workspace_id}/items/{item['id']}"
        self.rest.call("DELETE", url, FABRIC)
        for _ in range(24):  # item deletion can complete asynchronously
            status, _ = self.rest.call("GET", url, FABRIC)
            if status == 404:
                self._record(label, item["name"])
                self.report.log("success", f"Deleted {label} '{item['name']}'")
                return
            self._sleep(5)
        raise RuntimeError(f"{label} '{item['name']}' still exists 2 minutes after delete")

    def _delete_front_end_apps(self, plan: TeardownPlan) -> None:
        if not plan.app_backends:
            self.report.log("info", "No Rayfin apps in the workspace")
        for backend in plan.app_backends:
            self._delete_item(plan, backend, "AppBackend")
        for item in plan.companion_items:
            self._delete_item(plan, item, item["type"])

    def _delete_unity_catalog(self, plan: TeardownPlan) -> None:
        connectors = set(plan.connector_ids)
        for url in plan.databricks_urls:
            base = f"https://{url}/api/2.1/unity-catalog"
            credentials = [c for c in self._uc_list(f"{base}/storage-credentials", "storage_credentials")
                           if ((c.get("azure_managed_identity") or {}).get("access_connector_id") or "").lower() in connectors]
            names = {c["name"] for c in credentials}
            locations = [l for l in self._uc_list(f"{base}/external-locations", "external_locations")
                         if l.get("credential_name") in names]
            roots = [l["url"].rstrip("/") + "/" for l in locations if l.get("url")]
            catalogs = [c for c in self._uc_list(f"{base}/catalogs", "catalogs")
                        if any(((c.get("storage_root") or c.get("storage_location") or "").rstrip("/") + "/").startswith(r) for r in roots)]
            for kind, objects, path in (("catalog", catalogs, "catalogs"), ("external location", locations, "external-locations"),
                                        ("storage credential", credentials, "storage-credentials")):
                for obj in objects:
                    name = urllib.parse.quote(obj["name"], safe="")
                    self.rest.call("DELETE", f"{base}/{path}/{name}?force=true", DATABRICKS)
                    self._record(f"Unity Catalog {kind}", obj["name"])
                    self.report.log("success", f"Deleted Unity Catalog {kind} '{obj['name']}'")
            if not (catalogs or locations or credentials):
                self.report.log("info", f"No Unity Catalog objects bound to this deployment in {url}")

    def _uc_list(self, url: str, key: str) -> list[dict]:
        rows: list[dict] = []
        token = ""
        while True:
            _, body = self.rest.call("GET", url + (f"?page_token={urllib.parse.quote(token)}" if token else ""), DATABRICKS)
            rows.extend((body or {}).get(key) or [])
            token = (body or {}).get("next_page_token") or ""
            if not token:
                return rows

    def _delete_connections(self, plan: TeardownPlan) -> None:
        hosts = [t for t in plan.tie_values if "." in t]
        count = 0
        for connection in self.rest.pages(f"{FABRIC}/v1/connections", FABRIC):
            path = str(((connection.get("connectionDetails") or {}).get("path")) or "").lower()
            if path and any(h in path for h in hosts):
                self.rest.call("DELETE", f"{FABRIC}/v1/connections/{connection['id']}", FABRIC)
                self._record("Fabric connection", connection.get("displayName", connection["id"]))
                self.report.log("success", f"Deleted Fabric connection '{connection.get('displayName')}'")
                count += 1
        if not count:
            self.report.log("info", "No Fabric connections point at this deployment's endpoints")

    def _graph_delete_apps(self, display_name: str, owner_prefix: str | None) -> None:
        query = urllib.parse.quote(f"displayName eq '{display_name.replace(chr(39), chr(39) * 2)}'")
        for app in self.rest.pages(f"{GRAPH}/v1.0/applications?$filter={query}&$select=id,appId,displayName,tags", GRAPH):
            if owner_prefix is not None and not any(str(t).lower().startswith(owner_prefix) for t in app.get("tags") or []):
                self.report.log("warn", f"Kept Entra app '{display_name}' ({app['appId']}): owner tag does not match this deployment")
                continue
            by_app = urllib.parse.quote(f"appId eq '{app['appId']}'")
            for sp in self.rest.pages(f"{GRAPH}/v1.0/servicePrincipals?$filter={by_app}&$select=id", GRAPH):
                self.rest.call("DELETE", f"{GRAPH}/v1.0/servicePrincipals/{sp['id']}", GRAPH)
            self.rest.call("DELETE", f"{GRAPH}/v1.0/applications/{app['id']}", GRAPH)
            self._record("Entra app", f"{display_name} ({app['appId']})")
            self.report.log("success", f"Deleted Entra app '{display_name}' and its service principal")
        if owner_prefix is None:  # the workspace identity's own service principal, if it outlived deprovisioning
            for sp in self.rest.pages(f"{GRAPH}/v1.0/servicePrincipals?$filter={query}&$select=id,appId,servicePrincipalType", GRAPH):
                if sp.get("servicePrincipalType") in ("ManagedIdentity", "Application"):
                    self.rest.call("DELETE", f"{GRAPH}/v1.0/servicePrincipals/{sp['id']}", GRAPH)
                    self._record("Entra service principal", f"{display_name} ({sp['appId']})")

    def _delete_workspace_identity(self, plan: TeardownPlan) -> None:
        try:
            self.rest.call("POST", f"{FABRIC}/v1/workspaces/{plan.workspace_id}/deprovisionIdentity", FABRIC)
            self.report.log("success", "Workspace identity deprovisioned")
        except HttpError as error:
            self.report.log("warn", f"Workspace identity deprovision: {error}")
        self._graph_delete_apps(self.spec.workspace_name, owner_prefix=None)

    def _delete_workspace(self, plan: TeardownPlan) -> None:
        self.rest.call("DELETE", f"{FABRIC}/v1/workspaces/{plan.workspace_id}", FABRIC)
        for _ in range(60):
            status, _ = self.rest.call("GET", f"{FABRIC}/v1/workspaces/{plan.workspace_id}", FABRIC)
            if status == 404:
                self._record("Fabric workspace", self.spec.workspace_name)
                self.report.log("success", f"Workspace '{self.spec.workspace_name}' deleted")
                return
            self._sleep(5)
        raise RuntimeError(f"workspace '{self.spec.workspace_name}' still exists 5 minutes after delete")

    def _delete_front_end_identities(self, plan: TeardownPlan) -> None:
        for front_end in plan.front_ends:
            if front_end.delete:
                prefix = f"{CARDIOLOGY_OWNER_TAG}{self.spec.subscription_id}/{front_end.name}/".lower()
                self._graph_delete_apps(f"cardiology-app-{front_end.name}", owner_prefix=prefix)

    def _delete_groups(self, groups: list[str]) -> None:
        for group in groups:
            self.rest.call("DELETE", self._arm(f"/resourcegroups/{group}?api-version=2021-04-01"), ARM)
            self.report.log("info", f"Deleting resource group '{group}'")
        pending = list(groups)
        for _ in range(max(1, self.spec.wait_minutes * 4)):  # one check every 15 s
            for group in list(pending):
                status, _ = self.rest.call("GET", self._arm(f"/resourcegroups/{group}?api-version=2021-04-01"), ARM)
                if status == 404:
                    pending.remove(group)
                    self._record("Resource group", group)
                    self.report.log("success", f"Resource group '{group}' deleted")
            if not pending:
                break
            self._sleep(15)
        if pending:
            raise RuntimeError(f"still deleting after {self.spec.wait_minutes} min: {', '.join(pending)}")

    def _verify(self, plan: TeardownPlan) -> None:
        problems: list[str] = []
        if self.spec.delete_workspace and plan.workspace_id:
            status, _ = self.rest.call("GET", f"{FABRIC}/v1/workspaces/{plan.workspace_id}", FABRIC)
            if status != 404:
                problems.append(f"workspace '{self.spec.workspace_name}' still exists")
        groups = [f.name for f in plan.front_ends if f.delete]
        if self.spec.delete_azure_rg and plan.main_group_exists:
            groups.append(self.spec.resource_group_name)
        for group in groups:
            status, _ = self.rest.call("GET", self._arm(f"/resourcegroups/{group}?api-version=2021-04-01"), ARM)
            if status != 404:
                problems.append(f"resource group '{group}' still exists")
        if problems:
            raise RuntimeError("; ".join(problems))
        self.report.log("success", "Verified: every targeted workspace and resource group is gone")


# --------------------------------------------------------------------------- CLI


class _PrintReport:
    def log(self, level: str, message: str) -> None:
        print(f"  [{level}] {message}", flush=True)

    def phase(self, name: str, status: str) -> None:
        print(f"== {name}: {status}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tear down one HLS deployment and its front ends.")
    parser.add_argument("--workspace", default="")
    parser.add_argument("--resource-group", default="")
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--expected-tenant", default="")
    parser.add_argument("--front-end-resource-group", action="append", default=[])
    parser.add_argument("--no-front-end-discovery", action="store_true")
    parser.add_argument("--delete-workspace", action="store_true")
    parser.add_argument("--delete-resource-group", action="store_true")
    parser.add_argument("--wait-minutes", type=int, default=45)
    parser.add_argument("--plan", action="store_true", help="discover and print the plan; delete nothing")
    args = parser.parse_args(argv)
    spec = TeardownSpec(
        workspace_name=args.workspace, resource_group_name=args.resource_group,
        delete_workspace=args.delete_workspace, delete_azure_rg=args.delete_resource_group,
        subscription_id=args.subscription, expected_tenant_id=args.expected_tenant,
        front_end_resource_groups=args.front_end_resource_group,
        discover_front_ends=not args.no_front_end_discovery, wait_minutes=args.wait_minutes)
    try:
        result = DeploymentTeardown(spec, AzureCliTokens(args.subscription), _PrintReport()).run(plan_only=args.plan)
    except TeardownRefused as refused:
        print(f"RESULT: {json.dumps({'status': 'refused', 'reason': str(refused)})}", flush=True)
        return 2
    print(f"RESULT: {json.dumps(result)}", flush=True)
    return 0 if args.plan or result.get("status") == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
