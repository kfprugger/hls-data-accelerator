from __future__ import annotations

import io
import itertools
import json
import re
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.full_teardown import (  # noqa: E402
    FABRIC,
    PHASE_CONNECTIONS,
    PHASE_PREFLIGHT,
    AzureCliTokens,
    DeploymentTeardown,
    IncompleteListing,
    Rest,
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
                 stuck_groups: set[str] | None = None, tenant: str = TENANT,
                 workspaces: list[dict] | None = None, workspace_items: dict[str, list[dict]] | None = None,
                 scripted: dict[str, list[tuple[int, object]]] | None = None) -> None:
        self.groups = groups
        self.container_apps = container_apps or []
        self.tagged_groups = tagged_groups or []
        self.entra_apps = entra_apps or []
        self.resource_bodies = {k.lower(): v for k, v in (resource_bodies or {}).items()}
        self.unity = unity or {}
        self.stuck_groups = stuck_groups or set()
        self.tenant = tenant
        self.workspaces = list(workspaces or [])
        self.workspace_items = {k.lower(): list(v) for k, v in (workspace_items or {}).items()}
        self.deleted_groups: set[str] = set()
        self.deleted_workspaces: set[str] = set()
        self.deleted_items: set[str] = set()
        self.scripted = {k.lower(): list(v) for k, v in (scripted or {}).items()}  # path -> successive GET replies
        self.calls: list[tuple[str, str]] = []

    def deletes(self) -> list[str]:
        return [url for method, url in self.calls if method == "DELETE"]

    def call(self, method: str, url: str, resource: str, body=None):
        self.calls.append((method, url))
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        query = urllib.parse.unquote(parsed.query)
        if method == "GET" and self.scripted.get(path):
            return self.scripted[path].pop(0)
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
        if path == "/v1/workspaces":
            return 200, {"value": [w for w in self.workspaces if w["id"].lower() not in self.deleted_workspaces]}
        ws_item_match = re.fullmatch(r"/v1/workspaces/([^/]+)/items(?:/([^/]+))?", path)
        if ws_item_match:
            ws_id, item_id = ws_item_match.group(1), ws_item_match.group(2)
            if item_id:
                if method == "DELETE":
                    self.deleted_items.add(item_id)
                    return 200, {}
                return (404, None) if item_id in self.deleted_items else (200, {"id": item_id})
            return 200, {"value": [i for i in self.workspace_items.get(ws_id, []) if i["id"].lower() not in self.deleted_items]}
        ws_match = re.fullmatch(r"/v1/workspaces/([^/]+)", path)
        if ws_match:
            ws_id = ws_match.group(1)
            if method == "DELETE":
                self.deleted_workspaces.add(ws_id)
                return 200, {}
            return (404, None) if ws_id in self.deleted_workspaces else (200, {"id": ws_id})
        if path == "/v1/connections":
            return 200, {"value": []}
        return 404, None

    pages = Rest.pages  # the production collection contract over this fake transport


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

    def test_orphaned_rayfin_companion_items_are_deleted_when_app_backend_already_gone(self) -> None:
        cloud = FakeCloud(
            {"rg-main": MAIN_GROUP},
            workspaces=[{"id": "ws-1", "displayName": "med-1006"}],
            workspace_items={
                "ws-1": [
                    {"id": "sql-1", "displayName": "rayfin-health-command-center", "type": "SQLDatabase"},
                    {"id": "udf-1", "displayName": "rayfin-health-command-center", "type": "UserDataFunction"},
                    {"id": "sql-2", "displayName": "caldova-cardiology-app", "type": "SQLDatabase"},
                    {"id": "udf-2", "displayName": "rayfin-imaging", "type": "UserDataFunction"},
                    {"id": "lh-1", "displayName": "healthcare1_msft_silver", "type": "Lakehouse"},
                ]
            },
        )
        teardown, _ = _teardown(cloud, workspace_name="med-1006", delete_workspace=True, delete_azure_rg=True)

        result = teardown.run()

        self.assertEqual(result["status"], "succeeded", result.get("failures"))
        self.assertEqual(cloud.deleted_items, {"sql-1", "udf-1", "sql-2", "udf-2"})
        self.assertIn("ws-1", cloud.deleted_workspaces)

    def test_workspace_listed_on_a_later_page_is_torn_down(self) -> None:
        target = {"id": "ws-2", "displayName": "med-1006"}
        cloud = FakeCloud({"rg-main": MAIN_GROUP}, workspaces=[target], scripted={"/v1/workspaces": [
            (200, {"value": [{"id": "ws-1", "displayName": "another-deployment"}], "continuationToken": "page-2"}),
            (200, {"value": [target]}),
        ]})
        teardown, _ = _teardown(cloud, workspace_name="med-1006", delete_workspace=True)

        result = teardown.run()

        self.assertEqual(result["status"], "succeeded", result.get("failures"))
        self.assertEqual(cloud.deleted_workspaces, {"ws-2"})

    def test_unreadable_workspace_list_is_never_reported_as_absent(self) -> None:
        listed = (200, {"value": [{"id": "ws-0", "displayName": "another-deployment"}], "continuationToken": "page-2"})
        for name, replies in {
            "first page 404 (CapacityNotActive)": [(404, None)],
            "later page 404": [listed, (404, None)],
            "empty body": [(200, None)],
            "no value list": [(200, {"error": {"code": "Unknown"}})],
            "row without displayName": [(200, {"value": [{"id": "ws-1"}]})],
        }.items():
            with self.subTest(name):
                cloud = FakeCloud({"rg-main": MAIN_GROUP}, workspaces=[{"id": "ws-1", "displayName": "med-1006"}],
                                  scripted={"/v1/workspaces": replies})
                teardown, report = _teardown(cloud, workspace_name="med-1006", delete_workspace=True, delete_azure_rg=True)

                with self.assertRaises(IncompleteListing):
                    teardown.run()
                self.assertEqual(cloud.deletes(), [])
                self.assertEqual(report.phases[PHASE_PREFLIGHT], "failed")
                self.assertFalse([m for _, m in report.logs if "not found" in m])

    def test_failed_later_item_page_stops_the_workspace_teardown(self) -> None:
        cloud = FakeCloud({"rg-main": MAIN_GROUP}, workspaces=[{"id": "ws-1", "displayName": "med-1006"}],
                          scripted={"/v1/workspaces/ws-1/items": [
                              (200, {"value": [{"id": "lh-1", "displayName": "healthcare1_msft_silver", "type": "Lakehouse"}],
                                     "continuationUri": f"{FABRIC}/v1/workspaces/ws-1/items?continuationToken=page-2"}),
                              (404, None),
                          ]})
        teardown, _ = _teardown(cloud, workspace_name="med-1006", delete_workspace=True, delete_azure_rg=True)

        with self.assertRaises(IncompleteListing):
            teardown.run()
        self.assertEqual(cloud.deletes(), [])

    def test_unreadable_connection_list_fails_its_phase_instead_of_claiming_none(self) -> None:
        cloud = FakeCloud({"rg-main": MAIN_GROUP}, scripted={"/v1/connections": [(404, None)]})
        teardown, report = _teardown(cloud, delete_azure_rg=True)

        result = teardown.run()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(report.phases[PHASE_CONNECTIONS], "failed")
        self.assertNotIn(("info", "No Fabric connections point at this deployment's endpoints"), report.logs)


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


class _Response:
    def __init__(self, status: int, raw: bytes) -> None:
        self.status = status
        self._raw = raw

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


class FakeHttp:
    """urllib opener stand-in for Rest: answers by full URL (unknown URLs are 404) and records each request."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.sent: list[tuple[str, str | None]] = []  # (url, Authorization header)

    def __call__(self, request, timeout):
        url = request.full_url
        self.sent.append((url, request.get_header("Authorization")))
        status, body = self.answer(url) or (404, {"errorCode": "CapacityNotActive"})
        raw = b"" if body is None else json.dumps(body).encode()
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "error", {}, io.BytesIO(raw))
        return _Response(status, raw)


def _rest(answer) -> tuple[Rest, FakeHttp]:
    http = FakeHttp(answer)
    return Rest(Tokens(), opener=http, sleep=lambda _: None), http


class RestPagesTests(unittest.TestCase):
    def test_rows_on_later_pages_are_listed_for_every_continuation_style(self) -> None:
        items = f"{FABRIC}/v1/workspaces/ws-1/items?type=Lakehouse"
        arm = "https://management.azure.com/subscriptions/s/resourceGroups/rg/resources?api-version=2021-04-01"
        graph = "https://graph.microsoft.com/v1.0/applications?$filter=displayName%20eq%20'x'&$select=id,appId"
        for name, (first, extra, second) in {
            "ARM nextLink": (arm, {"nextLink": f"{arm}&%24skiptoken=p2"}, f"{arm}&%24skiptoken=p2"),
            "Graph @odata.nextLink": (graph, {"@odata.nextLink": f"{graph}&$skiptoken=p2"}, f"{graph}&$skiptoken=p2"),
            "Fabric continuationUri": (items, {"continuationUri": f"{items}&continuationToken=p2", "continuationToken": "p2"},
                                       f"{items}&continuationToken=p2"),
            "Fabric continuationToken only": (items, {"continuationToken": "p2"}, f"{items}&continuationToken=p2"),
        }.items():
            with self.subTest(name):
                rest, http = _rest({first: (200, {"value": [{"id": "a"}], **extra}),
                                    second: (200, {"value": [{"id": "target"}]})}.get)

                self.assertEqual([row["id"] for row in rest.pages(first, "resource", fields=("id",))], ["a", "target"])
                self.assertEqual([url for url, _ in http.sent], [first, second])

    def test_failed_or_malformed_pages_raise_instead_of_listing_nothing(self) -> None:
        first = f"{FABRIC}/v1/workspaces"
        later = f"{first}?continuationToken=p2"
        for name, replies in {
            "first page 404 (CapacityNotActive)": {},
            "later page 404": {first: (200, {"value": [{"id": "a"}], "continuationUri": later})},
            "204 without a body": {first: (204, None)},
            "body is not an object": {first: (200, [{"id": "a"}])},
            "no value key": {first: (200, {"items": []})},
            "value is not a list": {first: (200, {"value": None})},
            "row is not an object": {first: (200, {"value": ["a"]})},
            "row lacks a required field": {first: (200, {"value": [{"displayName": "x"}]})},
            "continuation is not a string": {first: (200, {"value": [], "continuationUri": 5})},
        }.items():
            with self.subTest(name):
                rest, _ = _rest(replies.get)

                with self.assertRaises(IncompleteListing):
                    list(rest.pages(first, FABRIC, fields=("id",)))

    def test_confirmed_empty_terminal_page_is_an_empty_collection(self) -> None:
        first = f"{FABRIC}/v1/connections"
        rest, http = _rest({first: (200, {"value": [], "continuationUri": None, "continuationToken": None})}.get)

        self.assertEqual(list(rest.pages(first, FABRIC, fields=("id",))), [])
        self.assertEqual(len(http.sent), 1)

    def test_unsafe_continuations_are_refused_before_the_token_is_sent(self) -> None:
        first = f"{FABRIC}/v1/workspaces"
        for name, link in {
            "other origin": "https://evil.example/v1/workspaces?continuationToken=p2",
            "plain http": "http://api.fabric.microsoft.com/v1/workspaces?continuationToken=p2",
            "userinfo host swap": "https://api.fabric.microsoft.com@evil.example/v1/workspaces",
            "other port": "https://api.fabric.microsoft.com:8443/v1/workspaces",
            "other path": f"{FABRIC}/v1/admin/workspaces?continuationToken=p2",
            "relative": "/v1/workspaces?continuationToken=p2",
        }.items():
            with self.subTest(name):
                rest, http = _rest(lambda url, link=link: (200, {"value": [{"id": "a"}], "continuationUri": link})
                                   if url == first else (200, {"value": []}))

                with self.assertRaises(IncompleteListing):
                    list(rest.pages(first, FABRIC))
                self.assertEqual([url for url, _ in http.sent], [first])

    def test_repeating_or_endless_continuations_stop(self) -> None:
        first = f"{FABRIC}/v1/workspaces"
        second = f"{first}?continuationToken=p2"
        rest, http = _rest({first: (200, {"value": [{"id": "a"}], "continuationUri": second}),
                            second: (200, {"value": [{"id": "b"}], "continuationUri": first})}.get)
        with self.assertRaises(IncompleteListing):
            list(rest.pages(first, FABRIC))
        self.assertEqual(len(http.sent), 2)

        tokens = itertools.count()
        rest, http = _rest(lambda url: (200, {"value": [], "continuationToken": f"t{next(tokens)}"}))
        with mock.patch("shared.full_teardown.MAX_LIST_PAGES", 5), self.assertRaises(IncompleteListing):
            list(rest.pages(first, FABRIC))
        self.assertEqual(len(http.sent), 5)


if __name__ == "__main__":
    unittest.main()
