"""Authentication and lifecycle rules, without network or process state."""

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import UUID

SESSION_SECONDS = 8 * 60 * 60
HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "proxy-connection",
})


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str
    session_key: str
    public_base_url: str
    allowed_users: frozenset[tuple[str, str]]
    allowed_tenants: frozenset[str]
    subscription_id: str
    resource_group: str
    environment_id: str
    environment_domain: str
    sandbox_image: str
    sandbox_identity_id: str
    storage_account: str
    azure_client_id: str
    max_sandboxes: int = 5
    idle_minutes: int = 120

    @classmethod
    def from_env(cls):
        def required(name):
            value = os.environ.get(name, "").strip()
            if not value:
                raise ValueError(f"{name} is required")
            return value

        def allowlist(name):
            return frozenset(x.strip().lower() for x in os.environ.get(name, "").split(",") if x.strip())

        users = set()
        for entry in allowlist("HLS_ALLOWED_USERS"):
            tid, separator, identity = entry.partition(":")
            if not separator or not identity or ":" in identity or any(c.isspace() for c in identity):
                raise ValueError("HLS_ALLOWED_USERS entries must be <tenant GUID>:<email or object GUID>")
            if "@" not in identity:
                identity = str(UUID(identity))
            users.add((str(UUID(tid)), identity))

        settings = cls(
            client_id=required("HLS_CLIENT_ID"), client_secret=required("HLS_CLIENT_SECRET"),
            session_key=required("HLS_SESSION_KEY"),
            public_base_url=required("HLS_PUBLIC_BASE_URL").rstrip("/"),
            allowed_users=frozenset(users),
            allowed_tenants=frozenset(str(UUID(tid)) for tid in allowlist("HLS_ALLOWED_TENANTS")),
            subscription_id=required("HLS_SUBSCRIPTION_ID"),
            resource_group=required("HLS_RESOURCE_GROUP"),
            environment_id=required("HLS_ENVIRONMENT_ID"),
            environment_domain=required("HLS_ENV_DEFAULT_DOMAIN"),
            sandbox_image=required("HLS_SANDBOX_IMAGE"),
            sandbox_identity_id=required("HLS_SANDBOX_IDENTITY_ID"),
            storage_account=required("HLS_STORAGE_ACCOUNT"),
            azure_client_id=required("AZURE_CLIENT_ID"),
            max_sandboxes=int(os.environ.get("HLS_MAX_SANDBOXES", "5")),
            idle_minutes=int(os.environ.get("HLS_IDLE_MINUTES", "120")),
        )
        if settings.max_sandboxes < 1 or settings.idle_minutes < 1:
            raise ValueError("Sandbox and idle limits must be positive")
        if not settings.public_base_url.startswith("https://"):
            raise ValueError("HLS_PUBLIC_BASE_URL must use HTTPS")
        return settings


@dataclass(frozen=True)
class User:
    email: str
    oid: str
    tid: str

    @classmethod
    def from_claims(cls, claims: Mapping):
        tid, oid = claims.get("tid"), claims.get("oid")
        if not isinstance(tid, str) or not tid.strip() or not isinstance(oid, str) or not oid.strip():
            raise ValueError("Sign-in did not include a tenant ID and object ID")
        email = next((claims.get(k) for k in ("preferred_username", "email", "upn")
                      if isinstance(claims.get(k), str) and claims[k].strip()), "")
        return cls(email.strip().lower(), str(UUID(oid.strip())), str(UUID(tid.strip())))

    @property
    def key(self):
        return hashlib.sha256(f"{self.tid}:{self.oid}".encode()).hexdigest()[:12]

    @property
    def app_name(self):
        return f"hls-sbx-{self.key}"


def allowed(user: User, settings: Settings) -> bool:
    return (user.tid, user.oid) in settings.allowed_users or (user.tid, user.email) in settings.allowed_users or user.tid in settings.allowed_tenants


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Activity timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def clean_headers(headers: list[tuple[bytes, bytes]], *, request: bool = False):
    connection_tokens = {
        part.strip().lower()
        for key, value in headers if key.lower() == b"connection"
        for part in value.decode("latin-1").split(",")
    }
    blocked = HOP_HEADERS | connection_tokens
    if request:
        blocked |= {"host", "cookie", "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"}
    else:
        # Sandbox responses cannot replace the gateway's authentication cookie.
        blocked |= {"set-cookie"}
    return [(k, v) for k, v in headers
            if k.decode("latin-1").lower() not in blocked
            and not k.lower().startswith(b"x-hls-")]


def proxy_headers(headers: list[tuple[bytes, bytes]], user: User, gateway_key: str):
    return clean_headers(headers, request=True) + [
        (b"x-hls-gateway-key", gateway_key.encode()),
        (b"x-hls-user-email", user.email.encode()),
        (b"x-hls-user-oid", user.oid.encode()),
        (b"x-hls-user-tid", user.tid.encode()),
    ]


def reaper_decision(*, now: datetime, last_seen: datetime, idle_minutes: int,
                    activity: dict | None, unreachable_since: datetime | None) -> tuple[bool, str]:
    """Only stale traffic AND stale work permit eviction; unknown work fails closed."""
    cutoff = now - timedelta(minutes=idle_minutes)
    if last_seen >= cutoff:
        return False, "recent gateway activity"
    if activity is None:
        if unreachable_since is not None and unreachable_since < cutoff:
            return True, "unreachable beyond idle limit"
        return False, "unreachable; grace period"
    active_runs = activity.get("active_runs")
    if type(active_runs) is not int or active_runs < 0:
        return False, "invalid activity response"
    if active_runs:
        return False, "active runs"
    try:
        last_activity = timestamp(activity["last_activity"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False, "invalid activity timestamp"
    if last_activity >= cutoff:
        return False, "recent sandbox activity"
    return True, "idle"
