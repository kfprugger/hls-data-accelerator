from __future__ import annotations

import json
import re
import sys
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.full_teardown import (  # noqa: E402
    AzureCliTokens,
    DeploymentTeardown,
    TeardownRefused,
    TeardownSpec,
)

SUB = "11111111-1111-1111-1111-111111111111"
TENANT = "tenant-a"


def _rid(group: str, kind: str, name: str) -> str:
    return f"/subscriptions/{SUB}/resourceGroups/{group}/providers/{kind}/{name}"


class FakeCloud:
    """In-memory ARM, Resource Graph, Microsoft Graph, Fabric and Unity Catalog."""

    def __init__(self, groups: dict[str, list[dict]], container_apps: list[dict] | None = None,
                 tagged_groups: list[str] | None = None, entra_apps: list[dict] | None = None,
                 resource_bodies: dict[str, dict] | None = None, unity: dict[str, list[dict]] | None = None,
                 stuck_groups: set[str] | None = None, tenant: str = TENANT) -> None:
        self.groups = groups
        self.container_apps = container_apps or []
        self.tagged_groups = tagged_groups or []
        self.entra_apps = entra_apps or []
        self.resource_bodies = {k.lower(): v for k, v in (resource_bodies or {}).items()}
        self.unity = unity or {}
        self.stuck_groups = stuck_groups or set()
        self.tenant = tenant
        self.deleted_groups: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def deletes(self) -> list[str]:
        return [url for method, url in self.calls if method == "DELETE"]

    def call(self, method: str, url: str, resource: str, body=None):
        self.calls.append((method, url))
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        query = urllib.parse.unquote(parsed.query)
        if "microsoft.resourcegraph" in path:
            if "containerapps" in body["query"]:
                return 200, {"data": self.container_apps}
            return 200, {"data": [{"name": g} for g in self.tagged_groups]}
        if path == f"/subscriptions/{SUB}":
            return 200, {"tenantId": self.tenant}
        group_match = re.fullmatch(rf"/subscriptions/{SUB}/resourcegroups/([^/]+)(/resources)?", path)
        if group_match:
            group = group_match.group(1)
            if method == "DELETE":
                self.deleted_groups.add(group)
                return 202, None
            gone = group not in self.groups or (group in self.deleted_groups and group not in self.stuck_groups)
            if gone:
                return 404, None
            if group_match.group(2):
                return 200, {"value": self.groups[group]}
            return 200, {"properties": {"provisioningState": "Succeeded"}}
        if path in self.resource_bodies:
            return 200, self.resource_bodies[path]
        if path == "/v1.0/applications":
            name = re.search(r"displayName eq '([^']*)'", query).group(1)
            return 200, {"value": [a for a in self.entra_apps if a["displayName"] == name]}
        if path.startswith("/v1.0/"):
            return (204, None) if method == "DELETE" else (200, {"value": []})
        if "/unity-catalog/" in path:
            if method == "DELETE":
                return 200, {}
            key = path.rsplit("/", 1)[1].replace("-", "_")
            return 200, {key: self.unity.get(key, [])}
        if path in ("/v1/workspaces", "/v1/connections"):
            return 200, {"value": []}
        return 404, None

    def pages(self, url: str, resource: str, key: str = "value"):
        status, body = self.call("GET", url, resource)
        if status == 404 or not body:
            return
        yield from body.get(key) or []


class Tokens:
    def __init__(self, tenant: str = TENANT) -> None:
        self.tenant_id = tenant

    def token(self, resource: str) -> str:
        return "token"


class Report:
    def __init__(self) -> None:
        self.phases: dict[str, str] = {}
        self.logs: list[tuple[str, str]] = []

    def log(self, level: str, message: str) -> None:
        self.logs.append((level, message))

    def phase(self, name: str, status: str) -> None:
        self.phases[name] = status


def _teardown(cloud: FakeCloud, tokens: Tokens | None = None, **spec) -> tuple[DeploymentTeardown, Report]:
    spec.setdefault("subscription_id", SUB)
    spec.setdefault("resource_group_name", "rg-main")
    report = Report()
    teardown = DeploymentTeardown(TeardownSpec(**spec), tokens or Tokens(), report, rest=cloud, sleep=lambda _: None)
    return teardown, report


MAIN_GROUP = [{"type": "Microsoft.Storage/storageAccounts", "name": "stmain",
               "id": _rid("rg-main", "Microsoft.Storage/storageAccounts", "stmain")}]


def _container_app(group: str, name: str, env_value: str) -> dict:
    return {"id": _rid(group, "Microsoft.App/containerApps", name), "name": name, "resourceGroup": group,
            "containers": [{"env": [{"name": "ENDPOINT", "value": env_value}]}]}


class FullTeardownSafetyTests(unittest.TestCase):
    def test_subscription_in_another_tenant_is_refused_before_any_delete(self) -> None:
        cloud = FakeCloud({"rg-main": MAIN_GROUP}, tenant="tenant-b")
        teardown, _ = _teardown(cloud, tokens=Tokens("tenant-b"), expected_tenant_id=TENANT, delete_azure_rg=True)

        with self.assertRaises(TeardownRefused):
            teardown.run()
        self.assertEqual(cloud.deletes(), [])

    def test_missing_subscription_is_refused(self) -> None:
        cloud = FakeCloud({"rg-main": MAIN_GROUP})
        teardown, _ = _teardown(cloud, subscription_id="", delete_azure_rg=True)

        with self.assertRaises(TeardownRefused):
            teardown.run()
        self.assertEqual(cloud.calls, [])

    def test_group_holding_a_fabric_capacity_refuses_the_whole_teardown(self) -> None:
        cloud = FakeCloud({
            "rg-main": MAIN_GROUP,
            "rg-cap": [{"type": "Microsoft.Fabric/capacities", "name": "cap",
                        "id": _rid("rg-cap", "Microsoft.Fabric/capacities", "cap")}],
        })
        teardown, _ = _teardown(cloud, delete_azure_rg=True, front_end_resource_groups=["rg-cap"])

        with self.assertRaises(TeardownRefused):
            teardown.run()
        self.assertEqual(cloud.deletes(), [])

    def test_explicit_group_with_nothing_tied_to_the_deployment_is_refused(self) -> None:
        cloud = FakeCloud({
            "rg-main": MAIN_GROUP,
            "rg-other": [{"type": "Microsoft.Storage/storageAccounts", "name": "stother",
                          "id": _rid("rg-other", "Microsoft.Storage/storageAccounts", "stother")}],
        })
        teardown, _ = _teardown(cloud, delete_azure_rg=True, front_end_resource_groups=["rg-other"])

        with self.assertRaises(TeardownRefused):
            teardown.run()
        self.assertEqual(cloud.deletes(), [])

    def test_old_function_and_static_site_names_do_not_establish_ownership(self) -> None:
        cloud = FakeCloud({
            "rg-main": MAIN_GROUP,
            "rg-old-host": [
                {"type": "Microsoft.Web/sites", "name": "medorch-func", "id": _rid("rg-old-host", "Microsoft.Web/sites", "medorch-func")},
                {"type": "Microsoft.Web/staticSites", "name": "medorch-swa", "id": _rid("rg-old-host", "Microsoft.Web/staticSites", "medorch-swa")},
            ],
        })
        teardown, _ = _teardown(cloud, front_end_resource_groups=["rg-old-host"])
        with self.assertRaises(TeardownRefused):
            teardown.run()
        self.assertEqual(cloud.deletes(), [])

    def test_owned_front_end_is_deleted_and_shared_group_is_kept_with_reason(self) -> None:
        tie = "https://stmain.blob.core.windows.net/data"
        cloud = FakeCloud(
            {
                "rg-main": MAIN_GROUP,
                "rg-front": [
                    {"type": "Microsoft.App/containerApps", "name": "app1", "id": _rid("rg-front", "Microsoft.App/containerApps", "app1")},
                    {"type": "Microsoft.App/managedEnvironments", "name": "env", "id": _rid("rg-front", "Microsoft.App/managedEnvironments", "env")},
                ],
                "rg-shared": [
                    {"type": "Microsoft.App/containerApps", "name": "app2", "id": _rid("rg-shared", "Microsoft.App/containerApps", "app2")},
                    {"type": "Microsoft.Sql/servers", "name": "sql1", "id": _rid("rg-shared", "Microsoft.Sql/servers", "sql1")},
                ],
            },
            container_apps=[_container_app("rg-front", "app1", tie), _container_app("rg-shared", "app2", tie)],
        )
        teardown, _ = _teardown(cloud, delete_azure_rg=True)

        result = teardown.run()

        self.assertEqual(result["status"], "succeeded", result.get("failures"))
        self.assertEqual(cloud.deleted_groups, {"rg-front", "rg-main"})
        self.assertEqual([s["name"] for s in result["skipped"]], ["rg-shared"])
        self.assertIn("sql1", result["skipped"][0]["skip_reason"])

    def test_cardiology_entra_app_owned_by_another_deployment_is_kept(self) -> None:
        tie = "https://stmain.blob.core.windows.net/data"
        cloud = FakeCloud(
            {
                "rg-main": MAIN_GROUP,
                "rg-front": [{"type": "Microsoft.App/containerApps", "name": "app1",
                              "id": _rid("rg-front", "Microsoft.App/containerApps", "app1")}],
            },
            container_apps=[_container_app("rg-front", "app1", tie)],
            entra_apps=[
                {"id": "obj-mine", "appId": "app-mine", "displayName": "cardiology-app-rg-front",
                 "tags": [f"hls-cardiology-app:{SUB}/rg-front/cardioe2e-app"]},
                {"id": "obj-theirs", "appId": "app-theirs", "displayName": "cardiology-app-rg-front",
                 "tags": ["hls-cardiology-app:22222222-2222-2222-2222-222222222222/rg-front/cardioe2e-app"]},
            ],
        )
        teardown, _ = _teardown(cloud, delete_azure_rg=True)

        teardown.run()

        app_deletes = [u for u in cloud.deletes() if "/v1.0/applications/" in u]
        self.assertEqual([u.rsplit("/", 1)[1] for u in app_deletes], ["obj-mine"])

    def test_only_unity_catalog_objects_bound_to_this_deployments_connector_are_deleted(self) -> None:
        connector = _rid("rg-main", "Microsoft.Databricks/accessConnectors", "conn")
        workspace = _rid("rg-main", "Microsoft.Databricks/workspaces", "dbw")
        cloud = FakeCloud(
            {"rg-main": MAIN_GROUP + [
                {"type": "Microsoft.Databricks/accessConnectors", "name": "conn", "id": connector},
                {"type": "Microsoft.Databricks/workspaces", "name": "dbw", "id": workspace},
            ]},
            resource_bodies={workspace: {"properties": {"workspaceUrl": "adb-1.azuredatabricks.net"}}},
            unity={
                "storage_credentials": [
                    {"name": "cred-mine", "azure_managed_identity": {"access_connector_id": connector}},
                    {"name": "cred-theirs", "azure_managed_identity": {"access_connector_id": "/other/connector"}},
                ],
                "external_locations": [
                    {"name": "loc-mine", "credential_name": "cred-mine", "url": "abfss://c@stmain.dfs.core.windows.net/"},
                    {"name": "loc-theirs", "credential_name": "cred-theirs", "url": "abfss://c@other.dfs.core.windows.net/"},
                ],
                "catalogs": [
                    {"name": "cat-mine", "storage_root": "abfss://c@stmain.dfs.core.windows.net/dev"},
                    {"name": "cat-theirs", "storage_root": "abfss://c@other.dfs.core.windows.net/"},
                    {"name": "system"},
                ],
            },
        )
        teardown, _ = _teardown(cloud, delete_azure_rg=True)

        teardown.run()

        uc_deletes = sorted(urllib.parse.urlparse(u).path.rsplit("/", 1)[1] for u in cloud.deletes() if "unity-catalog" in u)
        self.assertEqual(uc_deletes, ["cat-mine", "cred-mine", "loc-mine"])

    def test_group_that_never_disappears_fails_the_teardown(self) -> None:
        cloud = FakeCloud({"rg-main": MAIN_GROUP}, stuck_groups={"rg-main"})
        teardown, report = _teardown(cloud, delete_azure_rg=True, wait_minutes=1)

        result = teardown.run()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(report.phases["Azure Resource Group"], "failed")
        self.assertEqual(report.phases["Verification"], "failed")


class AzureCliTokenTests(unittest.TestCase):
    def test_tokens_from_different_tenants_are_refused(self) -> None:
        tenants = iter(["tenant-a", "tenant-b"])

        def runner(args, **kwargs):
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
                {"accessToken": "t", "tenant": next(tenants), "expires_on": 4102444800}))

        tokens = AzureCliTokens(SUB, runner=runner)
        tokens.token("https://management.azure.com")
        with self.assertRaises(TeardownRefused):
            tokens.token("https://graph.microsoft.com")




if __name__ == "__main__":
    unittest.main()
