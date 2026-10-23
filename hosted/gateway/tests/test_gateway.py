import asyncio
import copy
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from azure.mgmt.appcontainers.models import ContainerApp
from fastapi.testclient import TestClient

from hosted.gateway.app import create_app
from hosted.gateway.lifecycle import (
    ActiveRunsError, ActivityUnavailableError, AzureApps, BusyError, SandboxManager,
)
from hosted.gateway.policy import Settings, User, allowed, clean_headers, proxy_headers, reaper_decision

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
USER = User("joey@example.com", "d8d9c8bb-c184-4407-9a08-e1cda58b3bc1", "8d038e6a-9b7d-4cb8-bbcf-e84dff156478")
OTHER_TENANT = "c77e97fc-1859-4575-8c8b-53d74bc35a63"


@pytest.fixture
def settings():
    return Settings(
        client_id="portal-client", client_secret="test-client-secret", session_key="test-session-key" * 4,
        public_base_url="https://hls.test", allowed_users=frozenset({(USER.tid, USER.email)}), allowed_tenants=frozenset(),
        subscription_id="subscription", resource_group="rg-hls-deployer",
        environment_id="/subscriptions/subscription/resourceGroups/rg-hls-deployer/providers/Microsoft.App/managedEnvironments/cae-hls-deployer",
        environment_domain="environment.azurecontainerapps.io", sandbox_image="acrhlsdeployer.azurecr.io/hls-orchestrator-sandbox:new",
        sandbox_identity_id="/subscriptions/subscription/resourceGroups/rg-hls-deployer/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-hls-sandbox",
        storage_account="sthlsdeployer", azure_client_id="gateway-identity",
    )


@pytest.mark.parametrize("claims,expected", [
    ({"preferred_username": "  JOEY@EXAMPLE.COM  ", "tid": USER.tid.upper(), "oid": USER.oid.upper()}, True),
    ({"upn": USER.email, "tid": OTHER_TENANT, "oid": USER.oid}, False),
    ({"email": "different@example.com", "tid": USER.tid, "oid": USER.oid}, False),
    ({"tid": USER.tid, "oid": USER.oid}, False),
])
def test_allowlist_requires_matching_tenant_and_email(settings, claims, expected):
    assert allowed(User.from_claims(claims), settings) is expected


def test_object_entry_requires_matching_tenant(settings):
    settings = replace(settings, allowed_users=frozenset({(USER.tid, USER.oid)}))
    assert allowed(replace(USER, email=""), settings)
    assert not allowed(replace(USER, tid=OTHER_TENANT), settings)


def test_tenant_opt_in(settings):
    settings = replace(settings, allowed_users=frozenset(), allowed_tenants=frozenset({OTHER_TENANT}))
    assert allowed(replace(USER, tid=OTHER_TENANT, email="other@example.com"), settings)
    assert not allowed(USER, settings)


def test_environment_parses_tenant_pairs(settings, monkeypatch):
    for key in ("HLS_CLIENT_ID", "HLS_CLIENT_SECRET", "HLS_SESSION_KEY", "HLS_SUBSCRIPTION_ID",
                "HLS_RESOURCE_GROUP", "HLS_ENVIRONMENT_ID", "HLS_ENV_DEFAULT_DOMAIN", "HLS_SANDBOX_IMAGE",
                "HLS_SANDBOX_IDENTITY_ID", "HLS_STORAGE_ACCOUNT", "AZURE_CLIENT_ID"):
        monkeypatch.setenv(key, "test-value")
    monkeypatch.setenv("HLS_PUBLIC_BASE_URL", settings.public_base_url)
    monkeypatch.setenv("HLS_ALLOWED_USERS", f"{USER.tid.upper()}:JOEY@EXAMPLE.COM,{OTHER_TENANT}:{USER.oid.upper()}")
    monkeypatch.delenv("HLS_ALLOWED_TENANTS", raising=False)
    parsed = Settings.from_env()
    assert parsed.allowed_users == frozenset({(USER.tid, USER.email), (OTHER_TENANT, USER.oid)})
    assert not parsed.allowed_tenants
    monkeypatch.setenv("HLS_ALLOWED_TENANTS", OTHER_TENANT.upper())
    assert Settings.from_env().allowed_tenants == frozenset({OTHER_TENANT})
    for invalid in (USER.email, f"not-a-guid:{USER.email}", f"{USER.tid}:not-an-object-guid", f"{USER.tid}:"):
        monkeypatch.setenv("HLS_ALLOWED_USERS", invalid)
        with pytest.raises(ValueError):
            Settings.from_env()


def test_empty_allowlists_deny_everyone(settings):
    assert not allowed(USER, replace(settings, allowed_users=frozenset(), allowed_tenants=frozenset()))


@pytest.mark.parametrize("claims", [{"email": USER.email}, {"tid": "", "oid": USER.oid},
                                    {"tid": USER.tid, "oid": None}, {"tid": "bad", "oid": USER.oid},
                                    {"tid": USER.tid, "oid": "bad"}])
def test_identity_requires_tenant_and_object(claims):
    with pytest.raises(ValueError):
        User.from_claims(claims)


def test_naming_is_stable_and_tenant_scoped():
    key = hashlib.sha256(f"{USER.tid}:{USER.oid}".encode()).hexdigest()[:12]
    assert USER.key == key
    assert USER.app_name == "hls-sbx-" + key
    assert len(key) == 12 and int(key, 16) >= 0
    assert replace(USER, email="renamed@example.com").key == USER.key
    assert replace(USER, tid="other-tenant").key != USER.key
    assert replace(USER, oid="other-object").key != USER.key


def test_proxy_headers_remove_spoofing_and_hop_headers():
    result = proxy_headers([
        (b"Connection", b"keep-alive, X-Remove"), (b"X-Remove", b"bad"),
        (b"Keep-Alive", b"60"), (b"TE", b"trailers"), (b"Transfer-Encoding", b"chunked"),
        (b"X-HLS-Gateway-Key", b"forged"), (b"x-hLs-uSeR-oId", b"victim"),
        (b"X-HLS-Arbitrary", b"bad"), (b"Host", b"evil.example"),
        (b"Cookie", b"hls_session=secret"), (b"X-Forwarded-Host", b"evil"),
        (b"Accept", b"text/event-stream"), (b"Content-Type", b"application/json"),
    ], USER, "private-key")
    lowered = {k.lower(): v for k, v in result}
    assert lowered == {
        b"accept": b"text/event-stream", b"content-type": b"application/json",
        b"x-hls-gateway-key": b"private-key", b"x-hls-user-email": USER.email.encode(),
        b"x-hls-user-oid": USER.oid.encode(), b"x-hls-user-tid": USER.tid.encode(),
    }
    assert len(result) == len(lowered)


def test_response_header_duplicates_survive_without_hop_headers():
    assert clean_headers([(b"link", b"one"), (b"link", b"two"), (b"connection", b"x-private"),
                          (b"x-private", b"secret"), (b"x-hls-gateway-key", b"secret")]) == [(b"link", b"one"), (b"link", b"two")]


@pytest.mark.parametrize("seen,activity,unreachable,expected,reason", [
    (121, {"active_runs": 0, "last_activity": (NOW - timedelta(minutes=121)).isoformat()}, None, True, "idle"),
    (121, {"active_runs": 1, "last_activity": (NOW - timedelta(days=2)).isoformat()}, None, False, "active runs"),
    (120, {"active_runs": 0, "last_activity": (NOW - timedelta(days=2)).isoformat()}, None, False, "recent gateway activity"),
    (121, {"active_runs": 0, "last_activity": (NOW - timedelta(minutes=120)).isoformat()}, None, False, "recent sandbox activity"),
    (121, None, 121, True, "unreachable beyond idle limit"),
    (121, None, 120, False, "unreachable; grace period"),
    (121, None, None, False, "unreachable; grace period"),
    (1, None, 121, False, "recent gateway activity"),
    (121, {"active_runs": "0", "last_activity": NOW.isoformat()}, None, False, "invalid activity response"),
    (121, {"active_runs": 0, "last_activity": "invalid"}, None, False, "invalid activity timestamp"),
    (121, {"active_runs": 0, "last_activity": "2026-01-01T00:00:00"}, None, False, "invalid activity timestamp"),
])
def test_reaper_requires_both_idle_clocks(seen, activity, unreachable, expected, reason):
    assert reaper_decision(now=NOW, last_seen=NOW - timedelta(minutes=seen), idle_minutes=120,
                           activity=activity, unreachable_since=NOW - timedelta(minutes=unreachable) if unreachable else None) == (expected, reason)


class Registry:
    def __init__(self):
        self.rows, self.updates = {}, []

    def get(self, key):
        return copy.deepcopy(self.rows.get(key))

    def list(self):
        return copy.deepcopy(list(self.rows.values()))

    def create(self, row):
        assert row["RowKey"] not in self.rows
        self.rows[row["RowKey"]] = copy.deepcopy(row)

    def update(self, changes):
        self.updates.append(copy.deepcopy(changes))
        self.rows[changes["RowKey"]].update(changes)

    def delete(self, key):
        self.rows.pop(key, None)


class Apps:
    def __init__(self):
        self.existing, self.created, self.updated, self.deleted, self.restarted = {}, [], [], [], []

    def get(self, name):
        return copy.deepcopy(self.existing.get(name))

    def create(self, row):
        self.created.append(row["app_name"])

    def update_image(self, name, app):
        self.updated.append(name)

    def delete(self, name):
        self.deleted.append(name)

    def restart(self, name):
        self.restarted.append(name)


def services(settings, handler=None):
    def default(request):
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"active_runs": 0, "last_activity": NOW.isoformat()})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler or default))
    registry, apps = Registry(), Apps()
    return SandboxManager(settings, registry, apps, http)


def test_concurrent_admission_reserves_slots_before_provisioning(settings):
    async def scenario():
        manager = services(replace(settings, max_sandboxes=2))
        users = [replace(USER, oid=f"object-{i}") for i in range(6)]
        results = await asyncio.gather(*(manager.ensure(u) for u in users), return_exceptions=True)
        assert sum(isinstance(r, BusyError) for r in results) == 4
        assert len(manager.registry.rows) == 2
        assert await manager.ensure(users[0]) is results[0]
        assert len(manager.registry.rows) == 2
        await manager.close()
        assert len(manager.apps.created) == 2
        await manager.http.aclose()
    asyncio.run(scenario())


def test_container_contract_survives_sdk_serialization(settings):
    builder = object.__new__(AzureApps)
    builder.settings, builder.location = settings, "westus2"
    row = {"RowKey": USER.key, "gateway_key": "private-key", "email": USER.email, "oid": USER.oid, "tid": USER.tid}
    spec = ContainerApp(builder.spec(row)).as_dict()
    properties = spec["properties"]
    assert spec["location"] == "westus2"
    assert spec["identity"]["userAssignedIdentities"] == {settings.sandbox_identity_id: {}}
    assert properties["managedEnvironmentId"] == settings.environment_id
    config, template = properties["configuration"], properties["template"]
    assert config["ingress"]["external"] is False and config["ingress"]["targetPort"] == 7071
    assert config["registries"] == [{"server": "acrhlsdeployer.azurecr.io", "identity": settings.sandbox_identity_id}]
    assert config["secrets"] == [{"name": "gateway-key", "value": "private-key"}]
    assert template["scale"] == {"minReplicas": 1, "maxReplicas": 1}
    container = template["containers"][0]
    assert container["resources"] == {"cpu": 2, "memory": "4Gi"}
    assert container["volumeMounts"] == [{"volumeName": "sandboxes", "mountPath": "/data", "subPath": USER.key}]
    assert template["volumes"] == [{"name": "sandboxes", "storageType": "AzureFile", "storageName": "sandboxes",
                                    "mountOptions": "uid=10001,gid=10001,dir_mode=0750,file_mode=0640,nobrl,mfsymlinks,cache=strict"}]
    env = {entry["name"]: entry for entry in container["env"]}
    assert env["HLS_GATEWAY_KEY"] == {"name": "HLS_GATEWAY_KEY", "secretRef": "gateway-key"}
    assert env["HLS_HOSTED"]["value"] == "1"
    assert env["HLS_DATA_DIR"]["value"] == "/data"
    assert env["WARDFLOW_ROOT"]["value"] == "/app/wardflow"


@pytest.mark.parametrize("active,roll", [(0, True), (1, False), (None, False)])
def test_image_roll_only_when_activity_confirms_no_runs(settings, active, roll):
    async def scenario():
        manager = services(settings, lambda r: httpx.Response(503) if active is None else httpx.Response(
            200, json={"active_runs": active, "last_activity": NOW.isoformat()}))
        manager.apps.existing[USER.app_name] = {"properties": {"template": {"containers": [{"name": "sandbox", "image": "old"}]}}}
        await manager.ensure(USER)
        await manager.close()
        assert bool(manager.apps.updated) is roll
        assert not manager.apps.created
        # A deferred roll must not trigger an ARM reconciliation on every proxied request.
        await manager.ensure(USER)
        assert not manager.tasks
        await manager.http.aclose()
    asyncio.run(scenario())


def test_last_seen_writes_at_most_once_per_minute(settings, monkeypatch):
    async def scenario():
        clock = [NOW]
        monkeypatch.setattr("hosted.gateway.lifecycle.utcnow", lambda: clock[0])
        manager = services(settings)
        row = await manager.ensure(USER)
        await manager.close()
        for seconds in (1, 5, 20, 59, 60, 61, 90, 120):
            clock[0] = NOW + timedelta(seconds=seconds)
            await manager.touch(row)
        writes = [u for u in manager.registry.updates if "last_seen" in u]
        assert [u["last_seen"] for u in writes] == [(NOW + timedelta(seconds=s)).isoformat() for s in (60, 120)]
        await manager.http.aclose()
    asyncio.run(scenario())


def test_reaper_deletes_only_app_and_registry_after_unreachable_grace(settings, monkeypatch):
    async def scenario():
        clock = [NOW]
        monkeypatch.setattr("hosted.gateway.lifecycle.utcnow", lambda: clock[0])
        manager = services(settings, lambda r: httpx.Response(503))
        row = await manager.ensure(USER)
        await manager.close()
        clock[0] += timedelta(minutes=121)
        await manager.reap()
        assert not manager.apps.deleted
        assert manager.registry.rows[USER.key]["unreachable_since"] == clock[0].isoformat()
        clock[0] += timedelta(minutes=121)
        await manager.reap()
        await manager.close()
        assert manager.apps.deleted == [USER.app_name]
        assert not manager.registry.rows
        await manager.http.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize("active,error", [(1, ActiveRunsError), (None, ActivityUnavailableError)])
def test_restart_refuses_active_or_unknown_runs(settings, active, error):
    async def scenario():
        manager = services(settings, lambda r: httpx.Response(503) if active is None else httpx.Response(200, json={"active_runs": active}))
        await manager.ensure(USER)
        await manager.close()
        with pytest.raises(error):
            await manager.change(USER, "restart")
        assert not manager.apps.restarted
        await manager.http.aclose()
    asyncio.run(scenario())


class Login:
    def __init__(self, claims=None):
        self.claims = claims or {"preferred_username": USER.email, "tid": USER.tid, "oid": USER.oid}
        self.options = None

    def initiate_auth_code_flow(self, **kwargs):
        self.options = kwargs
        return {"auth_uri": "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?state=test-state",
                "state": "test-state", "code_verifier": "server-only-pkce-verifier"}

    def acquire_token_by_auth_code_flow(self, flow, response):
        if response.get("state") != flow["state"]:
            raise ValueError("state mismatch")
        assert flow["code_verifier"] == "server-only-pkce-verifier"
        return {"id_token_claims": self.claims, "access_token": "never-store-this-token"}


def sign_in(client):
    login = client.get("/auth/login", follow_redirects=False)
    assert login.status_code == 302
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    return client.get("/auth/callback", params={"code": "test-code", "state": state}, follow_redirects=False)


def test_sign_in_cookie_and_callback_allowlist(settings):
    manager, login = services(settings), Login()
    with TestClient(create_app(settings, manager, login), base_url=settings.public_base_url) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/anything").status_code == 401
        response = sign_in(client)
        assert response.status_code == 303 and response.headers["location"] == "/"
        cookie = response.headers["set-cookie"]
        assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and "Max-Age=28800" in cookie
        assert "never-store-this-token" not in cookie and "server-only-pkce-verifier" not in cookie
        assert login.options == {"scopes": ["email"], "redirect_uri": "https://hls.test/auth/callback"}
        assert USER.email in client.get("/gateway/me").text
        assert client.post("/auth/logout", headers={"Origin": "https://evil.test"}).status_code == 403
        assert client.post("/auth/logout", headers={"Origin": settings.public_base_url}).status_code == 200
        assert client.get("/gateway/status").status_code == 401
    asyncio.run(manager.http.aclose())


def test_denied_same_email_other_tenant_shows_identity_and_no_session(settings):
    manager = services(settings)
    login = Login({"email": USER.email, "tid": OTHER_TENANT, "oid": USER.oid})
    with TestClient(create_app(settings, manager, login), base_url=settings.public_base_url) as client:
        response = sign_in(client)
        assert response.status_code == 403
        assert USER.email in response.text and OTHER_TENANT in response.text and USER.oid in response.text
        assert "tenant ID and object ID" in response.text
        assert client.get("/gateway/status").status_code == 401
    asyncio.run(manager.http.aclose())


def test_callback_is_single_use_and_checks_state(settings):
    manager = services(settings)
    with TestClient(create_app(settings, manager, Login()), base_url=settings.public_base_url) as client:
        client.get("/auth/login", follow_redirects=False)
        assert client.get("/auth/callback?state=wrong&code=code").status_code == 400
        assert client.get("/auth/callback?state=test-state&code=code").status_code == 400
    asyncio.run(manager.http.aclose())


class Chunks(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        yield b"data: first\n\n"
        yield b"data: second\n\n"

    async def aclose(self):
        self.closed = True


def test_proxy_streams_and_preserves_encoded_url_and_headers(settings):
    captured, chunks = [], Chunks()

    async def handler(request):
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        captured.append((request, await request.aread()))
        return httpx.Response(200, headers=[(b"content-type", b"text/event-stream"), (b"connection", b"x-private"),
                                            (b"x-private", b"drop"), (b"link", b"one"), (b"link", b"two")], stream=chunks)

    manager = services(settings, handler)
    row = {"PartitionKey": "sbx", "RowKey": USER.key, "email": USER.email, "oid": USER.oid, "tid": USER.tid,
           "app_name": USER.app_name, "gateway_key": "private-key", "state": "ready", "created": NOW.isoformat(), "last_seen": NOW.isoformat()}
    manager.registry.create(row)
    manager.records[USER.key] = copy.deepcopy(row)
    manager.checked.add(USER.key)
    with TestClient(create_app(settings, manager, Login()), base_url=settings.public_base_url) as client:
        sign_in(client)
        response = client.post("/api/a%2Fb?x=one%2Ftwo", content=b'{"value":1}', headers={
            "Origin": settings.public_base_url, "X-HLS-Gateway-Key": "spoof", "X-HLS-User-Oid": "victim",
            "Content-Type": "application/json",
        })
        assert response.status_code == 200
        assert response.content == b"data: first\n\ndata: second\n\n"
        assert "x-private" not in response.headers and response.headers.get_list("link") == ["one", "two"]
        assert chunks.closed
        upstream, body = captured[0]
        assert upstream.url.raw_path == b"/api/a%2Fb?x=one%2Ftwo"
        assert upstream.url.host == f"{USER.app_name}.internal.{settings.environment_domain}"
        assert body == b'{"value":1}'
        assert upstream.headers["x-hls-gateway-key"] == "private-key"
        assert upstream.headers["x-hls-user-oid"] == USER.oid
        assert "cookie" not in upstream.headers
        assert client.post("/api/anything", headers={"Origin": "https://evil.test"}).status_code == 403
    asyncio.run(manager.http.aclose())
