"""Hosted HLS entrypoint. Run one worker: uvicorn gateway.app:app --port 8000."""

import asyncio
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from html import escape

import httpx
import msal
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware

from .lifecycle import (
    ActiveRunsError, ActivityUnavailableError, BusyError, SandboxManager, azure_services,
)
from .policy import SESSION_SECONDS, Settings, User, allowed, clean_headers, proxy_headers

log = logging.getLogger("hls.gateway")


def page(title, body, status=200):
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)} | HLS deployer</title>'
        '<style>body{font:17px system-ui;max-width:48rem;margin:4rem auto;padding:1rem;'
        'line-height:1.6}button{padding:.6rem 1rem;cursor:pointer}form{display:inline-block;'
        'margin-right:1rem}code{overflow-wrap:anywhere}a{color:#175fc1}</style>'
        f'<body><h1>{escape(title)}</h1>{body}</body></html>',
        status_code=status, headers={"Cache-Control": "no-store"},
    )


def waiting(next_path="/"):
    if not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"
    target = json.dumps(next_path).replace("<", "\\u003c")
    return page("Starting your sandbox", '<p id="status" role="status">Your workspace is starting. '
                'This can take a few minutes.</p><p><a href="/gateway/me">Manage your sandbox</a></p>'
                '<script>async function poll(){try{const r=await fetch("/gateway/status");'
                'if(r.status===401){location.assign("/auth/login");return;}'
                'const s=await r.json();if(s.state==="ready"){location.replace(' + target + ');return;}'
                'if(s.state==="error"){document.getElementById("status").textContent='
                '"Your sandbox could not start. Open Manage your sandbox to delete it and try again, '
                'or contact the operator.";return;}}catch(e){}setTimeout(poll,3000);}poll();</script>')


def create_app(settings=None, manager=None, msal_client=None):
    # Configuration is loaded when the app starts, not when tests import this module.
    @asynccontextmanager
    async def lifespan(app):
        config = settings or Settings.from_env()
        app.state.settings = config
        app.state.flows = {}
        app.state.msal = msal_client or await asyncio.to_thread(
            msal.ConfidentialClientApplication,
            config.client_id, client_credential=config.client_secret,
            authority="https://login.microsoftonline.com/organizations",
            exclude_scopes=["offline_access"],
        )
        credential = registry = apps = None
        http = manager.http if manager else httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15, read=None, write=120, pool=30), follow_redirects=False,
        )
        if manager is None:
            credential, registry, apps = azure_services(config)
        app.state.manager = manager or SandboxManager(config, registry, apps, http)
        app.state.http = http
        reaper = asyncio.create_task(app.state.manager.reaper_loop())
        try:
            yield
        finally:
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper
            await app.state.manager.close()
            if manager is None:
                await http.aclose()
                await asyncio.to_thread(registry.close)
                await asyncio.to_thread(apps.close)
                await asyncio.to_thread(credential.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    # SessionMiddleware needs its key before lifespan runs. A small ASGI wrapper below
    # initializes it from lifespan's validated config without reading env at import time.
    class SessionLayer:
        def __init__(self, app):
            self.app = app
            self.middleware = None

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                if self.middleware is None:
                    self.middleware = SessionMiddleware(
                        self.app, app.state.settings.session_key, session_cookie="hls_session",
                        max_age=SESSION_SECONDS, same_site="lax", https_only=True,
                    )
                await self.middleware(scope, receive, send)
            else:
                await self.app(scope, receive, send)

    app.add_middleware(SessionLayer)

    def user_for(request):
        identity = request.session.get("user")
        issued = request.session.get("issued_at", 0)
        if not isinstance(identity, dict) or not isinstance(issued, (int, float)) or time.time() - issued >= SESSION_SECONDS:
            request.session.clear()
            return None
        try:
            user = User.from_claims(identity)
        except ValueError:
            request.session.clear()
            return None
        if not allowed(user, app.state.settings):
            request.session.clear()
            return None
        return user

    def same_origin(request):
        return request.headers.get("origin", "").rstrip("/") == app.state.settings.public_base_url

    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def healthz():
        return {"status": "ok"}

    @app.get("/auth/login")
    async def login(request: Request):
        now = time.time()
        app.state.flows = {k: v for k, v in app.state.flows.items() if now - v[0] < 600}
        old_flow = request.session.pop("auth_flow_id", None)
        app.state.flows.pop(old_flow, None)
        # MSAL adds reserved openid/profile scopes and generates/verifies PKCE and nonce.
        flow = await asyncio.to_thread(
            app.state.msal.initiate_auth_code_flow, scopes=["email"],
            redirect_uri=app.state.settings.public_base_url + "/auth/callback",
        )
        flow_id = secrets.token_urlsafe(32)
        app.state.flows[flow_id] = (now, flow)
        request.session["auth_flow_id"] = flow_id
        return RedirectResponse(flow["auth_uri"], status_code=302)

    @app.get("/auth/callback")
    async def callback(request: Request):
        flow_id = request.session.pop("auth_flow_id", None)
        saved = app.state.flows.pop(flow_id, None)
        if saved is None or time.time() - saved[0] >= 600:
            return page("Sign-in expired", '<p><a href="/auth/login">Sign in again</a>.</p>', 400)
        try:
            result = await asyncio.to_thread(
                app.state.msal.acquire_token_by_auth_code_flow, saved[1], dict(request.query_params),
            )
        except ValueError:
            return page("Sign-in failed", '<p>The sign-in response was invalid. <a href="/auth/login">Try again</a>.</p>', 400)
        if "error" in result:
            return page("Sign-in failed", f'<p>{escape(result.get("error_description", result["error"]))}</p>', 400)
        try:
            user = User.from_claims(result.get("id_token_claims", {}))
        except ValueError as exc:
            return page("Sign-in failed", f"<p>{escape(str(exc))}</p>", 403)
        request.session.clear()
        if not allowed(user, app.state.settings):
            return page("Access not enabled", '<p>Send your tenant ID and object ID to the operator to request access.</p>'
                        f'<p>Email: <code>{escape(user.email or "not provided")}</code><br>'
                        f'Tenant ID: <code>{escape(user.tid)}</code><br>'
                        f'Object ID: <code>{escape(user.oid)}</code></p>', 403)
        request.session.update(user=asdict(user), issued_at=time.time(), csrf=secrets.token_urlsafe(32))
        return RedirectResponse("/", status_code=303)

    @app.post("/auth/logout")
    async def logout(request: Request):
        if not same_origin(request):
            return page("Request refused", "<p>Open the deployer to sign out.</p>", 403)
        flow_id = request.session.get("auth_flow_id")
        app.state.flows.pop(flow_id, None)
        request.session.clear()
        return page("Signed out", '<p>Your sandbox stays available until it becomes idle. '
                    '<a href="/auth/login">Sign in again</a>.</p>')

    @app.get("/gateway/status")
    async def status(request: Request):
        user = user_for(request)
        if user is None:
            return JSONResponse({"error": "Sign in required"}, status_code=401)
        row = await app.state.manager.ensure(user)
        await app.state.manager.touch(row)
        state = await app.state.manager.status(row)
        return JSONResponse({"state": state}, headers={"Cache-Control": "no-store"})

    @app.get("/gateway/me")
    async def me(request: Request):
        user = user_for(request)
        if user is None:
            return RedirectResponse("/auth/login", status_code=302)
        row = await app.state.manager.lookup(user)
        state = row["state"] if row else "not created"
        csrf = escape(request.session["csrf"], quote=True)
        forms = ''.join(
            f'<form method="post" action="/gateway/{action}"><input type="hidden" name="csrf" value="{csrf}">'
            f'<button type="submit">{action.title()}</button></form>' for action in ("restart", "delete")
        ) if row else ''
        return page("Your sandbox", f'<p>{escape(user.email)}<br>State: {escape(state)}</p>' + forms +
                    '<p>Restart and Delete are refused while a run is active. Delete keeps your saved history.</p>'
                    '<p><a href="/">Open deployer</a></p><form method="post" action="/auth/logout">'
                    '<button type="submit">Sign out</button></form>')

    @app.post("/gateway/{action}")
    async def change(action: str, request: Request):
        user = user_for(request)
        if user is None:
            return RedirectResponse("/auth/login", status_code=303)
        if action not in {"restart", "delete"}:
            return page("Not found", "<p>Unknown action.</p>", 404)
        if not same_origin(request):
            return page("Request refused", "<p>Use the buttons on your sandbox page.</p>", 403)
        from urllib.parse import parse_qs
        form = parse_qs((await request.body()).decode())
        csrf = form.get("csrf", [""])[0]
        if not secrets.compare_digest(csrf, request.session.get("csrf", "")):
            return page("Request refused", "<p>Reload your sandbox page and try again.</p>", 403)
        try:
            await app.state.manager.change(user, action)
        except (ActiveRunsError, ActivityUnavailableError, BusyError) as exc:
            return page("Sandbox unchanged", f'<p>{escape(str(exc))}</p><a href="/gateway/me">Back</a>', 409)
        return RedirectResponse("/gateway/me", status_code=303)

    @app.exception_handler(BusyError)
    async def busy(request, exc):
        if request.url.path == "/gateway/status":
            return JSONResponse({"state": "busy", "message": str(exc)}, status_code=503, headers={"Retry-After": "60"})
        response = page("The deployer is busy", f'<p>{escape(str(exc))}</p><p><a href="/">Try again</a></p>', 503)
        response.headers["Retry-After"] = "60"
        return response

    @app.exception_handler(PermissionError)
    async def identity_mismatch(request, exc):
        return page("Sandbox access refused", "<p>Contact the operator to resolve a sandbox identity conflict.</p>", 403)

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy(path: str, request: Request):
        if path == "healthz" or path.split("/", 1)[0] in {"auth", "gateway"}:
            return page("Not found", "<p>Unknown gateway route.</p>", 404)
        user = user_for(request)
        if user is None:
            if path.startswith("api/"):
                return JSONResponse({"error": "Sign in required"}, status_code=401)
            return RedirectResponse("/auth/login", status_code=302)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request):
            return JSONResponse({"error": "Cross-origin request refused"}, status_code=403)
        row = await app.state.manager.ensure(user)
        await app.state.manager.touch(row)
        if await app.state.manager.status(row) != "ready":
            if request.method in {"GET", "HEAD"} and not path.startswith("api/"):
                return waiting(request.url.path + ("?" + request.url.query if request.url.query else ""))
            return JSONResponse({"error": "Sandbox is starting", "status_url": "/gateway/status"}, status_code=503)
        # copy_with preserves the original percent-encoded path and query, not a decoded route value.
        url = httpx.URL(app.state.manager.url(row)).copy_with(
            raw_path=request.scope.get("raw_path", request.url.path.encode()) +
            (b"?" + request.scope["query_string"] if request.scope["query_string"] else b""),
        )
        upstream_request = app.state.http.build_request(
            request.method, url, headers=proxy_headers(list(request.headers.raw), user, row["gateway_key"]),
            content=request.stream(),
        )
        try:
            upstream = await app.state.http.send(upstream_request, stream=True)
        except httpx.HTTPError:
            log.warning("sandbox proxy unavailable app=%s", row["app_name"])
            await app.state.manager.save(row, state="starting")
            return JSONResponse({"error": "Sandbox temporarily unavailable"}, status_code=502)

        async def stream():
            try:
                async for chunk in upstream.aiter_raw():
                    await app.state.manager.touch(row)
                    yield chunk
            finally:
                await upstream.aclose()

        response = StreamingResponse(stream(), status_code=upstream.status_code)
        response.raw_headers = clean_headers(list(upstream.headers.raw))
        # StreamingResponse forwards each chunk directly, including SSE heartbeat frames.
        return response

    return app


app = create_app()
