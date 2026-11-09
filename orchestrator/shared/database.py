"""SQLite database for orchestrator state.

Consolidates all state previously spread across:
- .orchestrator-state.json (deployments, teardowns)
- localStorage teardown-locks (resource locks)
- localStorage teardown-dismissed (dismissed teardowns)
- localStorage form-history-* (form field history)

Tables:
- deployments: deployment/teardown instances with status, phases, logs
- locks: teardown resource locks (persisted across sessions)
- form_history: per-field input history for the deploy wizard
"""

import atexit
import os
import shutil
import tempfile
import json
import logging
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_persistent_dir = os.environ.get("HLS_DATA_DIR")
BACKUP_PATH = Path(_persistent_dir) / "orchestrator.db" if _persistent_dir else None
# Never open the live WAL database on the Azure Files SMB mount.
DB_PATH = Path(tempfile.mkdtemp(prefix="hls-orch-")) / "orchestrator.db" if BACKUP_PATH else Path(__file__).parent / "orchestrator.db"
_backup_dirty = threading.Event()
_backup_stop = threading.Event()
_backup_lock = threading.Lock()

if BACKUP_PATH:
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if BACKUP_PATH.exists():
        shutil.copyfile(BACKUP_PATH, DB_PATH)


class _PersistentConnection(sqlite3.Connection):
    def commit(self):
        super().commit()
        if BACKUP_PATH:
            _backup_dirty.set()


def backup_database() -> None:
    """Snapshot a committed local database atomically; no WAL lives on SMB."""
    if not BACKUP_PATH or not _backup_dirty.is_set():
        return
    with _backup_lock:
        _backup_dirty.clear()
        snapshot = DB_PATH.with_suffix(".snapshot.db")
        shared_snapshot = BACKUP_PATH.with_suffix(".db.tmp")
        try:
            with closing(sqlite3.connect(str(DB_PATH), timeout=30)) as source, closing(sqlite3.connect(str(snapshot))) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
            shutil.copyfile(snapshot, shared_snapshot)
            os.replace(shared_snapshot, BACKUP_PATH)
        except Exception:
            _backup_dirty.set()
            logger.exception("Persistent SQLite backup failed")
            raise
        finally:
            snapshot.unlink(missing_ok=True)
            shared_snapshot.unlink(missing_ok=True)


def _backup_worker() -> None:
    # A dirty commit is backed up within ten seconds (well below the 30s limit).
    while not _backup_stop.wait(10):
        try:
            backup_database()
        except Exception:
            pass  # Keep dirty state and retry; the error is logged above.


_backup_thread = threading.Thread(target=_backup_worker, name="sqlite-backup", daemon=True) if BACKUP_PATH else None
if _backup_thread:
    _backup_thread.start()


def shutdown_database() -> None:
    _backup_stop.set()
    if _backup_thread:
        _backup_thread.join()
    backup_database()


atexit.register(shutdown_database)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30, factory=_PersistentConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Wait (rather than immediately erroring) when another connection holds the
    # write lock — WAL permits one writer at a time across connections.
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# A single shared sqlite3.Connection is not safe for concurrent use across the
# FastAPI threadpool and asyncio background deploy tasks: overlapping execute()/
# commit() calls raise "InterfaceError: bad parameter or other API misuse" and can
# crash a background task mid-deploy. Give every thread its own connection, and
# serialize writes with a process-wide lock so commits never interleave.
_local = threading.local()
_write_lock = threading.RLock()
_init_lock = threading.Lock()
_initialized = False


def get_db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _get_conn()
        _local.conn = conn
    global _initialized
    if not _initialized:
        with _init_lock:
            if not _initialized:
                _init_tables(conn)
                _initialized = True
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS deployments (
            instance_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'deploy_all_orchestrator',
            runtime_status TEXT NOT NULL DEFAULT 'Running',
            created_time TEXT NOT NULL,
            last_updated_time TEXT NOT NULL,
            custom_status TEXT NOT NULL DEFAULT '{}',
            output TEXT,
            config TEXT
        );

        CREATE TABLE IF NOT EXISTS locks (
            resource_id TEXT PRIMARY KEY,
            resource_name TEXT,
            resource_type TEXT,
            locked_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS form_history (
            field TEXT NOT NULL,
            value TEXT NOT NULL,
            used_at TEXT NOT NULL,
            PRIMARY KEY (field, value)
        );

        CREATE TABLE IF NOT EXISTS dismissed_teardowns (
            instance_id TEXT PRIMARY KEY,
            dismissed_at TEXT NOT NULL
        );
    """)
    conn.commit()
    logger.info("SQLite database initialized at %s", DB_PATH)


# ── Deployment CRUD ────────────────────────────────────────────────────

def save_deployment(instance_id: str, data: dict[str, Any]):
    db = get_db()
    with _write_lock:
        db.execute("""
            INSERT OR REPLACE INTO deployments
                (instance_id, name, runtime_status, created_time, last_updated_time, custom_status, output, config)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            instance_id,
            data.get("name", ""),
            data.get("runtimeStatus", "Running"),
            data.get("createdTime", datetime.now(timezone.utc).isoformat()),
            data.get("lastUpdatedTime", datetime.now(timezone.utc).isoformat()),
            json.dumps(data.get("customStatus", {}), default=str),
            json.dumps(data.get("output"), default=str) if data.get("output") else None,
            json.dumps(data.get("config", {}), default=str),
        ))
        db.commit()


def get_deployment(instance_id: str) -> dict[str, Any] | None:
    db = get_db()
    row = db.execute(
        "SELECT * FROM deployments WHERE instance_id = ?", (instance_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_deployment(row)


def list_deployments() -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM deployments ORDER BY created_time DESC"
    ).fetchall()
    return [_row_to_deployment(r) for r in rows]


def delete_deployment(instance_id: str) -> bool:
    db = get_db()
    with _write_lock:
        cursor = db.execute(
            "DELETE FROM deployments WHERE instance_id = ?", (instance_id,)
        )
        db.commit()
    return cursor.rowcount > 0


def clear_all_deployments() -> int:
    db = get_db()
    with _write_lock:
        cursor = db.execute("DELETE FROM deployments")
        db.commit()
    return cursor.rowcount


def mark_stale_as_terminated():
    """Recover interrupted active runs, retaining completed estates for add-on retries."""
    db = get_db()
    with _write_lock:
        rows = db.execute(
            "SELECT instance_id, custom_status, output, created_time FROM deployments WHERE runtime_status IN ('Running', 'Pending')"
        ).fetchall()
        for row in rows:
            cs = json.loads(row["custom_status"])
            addon_only = bool(cs.get("addonRunBaseCompleted"))
            runtime_status = "Completed" if addon_only else "Terminated"
            cs["status"] = "succeeded" if addon_only else "terminated"
            cs["detail"] = "Server restarted — add-on interrupted; completed base deployment retained" if addon_only else "Server restarted — deployment was interrupted"
            if addon_only:
                cs["currentPhase"] = "Deployment Complete"
            for addon in cs.get("addons", {}).values():
                if addon.get("status") in {"pending", "running", "paused"}:
                    addon.update(status="failed", detail="Server restarted — restart this add-on", finishedAt=datetime.now(timezone.utc).isoformat())
            # Try to compute actual duration from phase data or last update
            output = json.loads(row["output"]) if row["output"] else None
            if output and "phases" in output:
                for phase in output["phases"]:
                    if phase.get("phase", "").startswith("Add-on:") and phase.get("status") in {"pending", "running", "paused"}:
                        phase.update(status="failed", detail="Server restarted — restart this add-on")
                phase_duration = sum(
                    p.get("duration", 0) for p in output["phases"]
                    if isinstance(p.get("duration"), (int, float))
                )
                if phase_duration > 0:
                    cs["durationSeconds"] = round(phase_duration, 1)
            db.execute("""
                UPDATE deployments
                SET runtime_status = ?,
                    custom_status = ?,
                    output = ?,
                    last_updated_time = ?
                WHERE instance_id = ?
            """, (runtime_status, json.dumps(cs, default=str), json.dumps(output, default=str) if output else None,
                  datetime.now(timezone.utc).isoformat(), row["instance_id"]))
            logger.warning("Recovered interrupted deployment %s as %s", row["instance_id"], runtime_status)
        db.commit()


def _row_to_deployment(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "instanceId": row["instance_id"],
        "name": row["name"],
        "runtimeStatus": row["runtime_status"],
        "createdTime": row["created_time"],
        "lastUpdatedTime": row["last_updated_time"],
        "customStatus": json.loads(row["custom_status"]),
        "output": json.loads(row["output"]) if row["output"] else None,
    }


# ── Locks ──────────────────────────────────────────────────────────────

def get_locks() -> list[str]:
    db = get_db()
    rows = db.execute("SELECT resource_id FROM locks").fetchall()
    return [r["resource_id"] for r in rows]


def set_lock(resource_id: str, name: str = "", resource_type: str = ""):
    db = get_db()
    with _write_lock:
        db.execute("""
            INSERT OR REPLACE INTO locks (resource_id, resource_name, resource_type, locked_at)
            VALUES (?, ?, ?, ?)
        """, (resource_id, name, resource_type, datetime.now(timezone.utc).isoformat()))
        db.commit()


def remove_lock(resource_id: str):
    db = get_db()
    with _write_lock:
        db.execute("DELETE FROM locks WHERE resource_id = ?", (resource_id,))
        db.commit()


def clear_locks():
    db = get_db()
    with _write_lock:
        db.execute("DELETE FROM locks")
        db.commit()


# ── Form History ───────────────────────────────────────────────────────

def get_form_history(field: str, limit: int = 10) -> list[str]:
    db = get_db()
    rows = db.execute(
        "SELECT value FROM form_history WHERE field = ? ORDER BY used_at DESC LIMIT ?",
        (field, limit),
    ).fetchall()
    return [r["value"] for r in rows]


def add_form_history(field: str, value: str):
    if not value.strip():
        return
    db = get_db()
    with _write_lock:
        db.execute("""
            INSERT OR REPLACE INTO form_history (field, value, used_at)
            VALUES (?, ?, ?)
        """, (field, value.strip(), datetime.now(timezone.utc).isoformat()))
        db.commit()


# ── Dismissed Teardowns ────────────────────────────────────────────────

def get_dismissed_teardowns() -> list[str]:
    db = get_db()
    rows = db.execute("SELECT instance_id FROM dismissed_teardowns").fetchall()
    return [r["instance_id"] for r in rows]


def dismiss_teardown(instance_id: str):
    db = get_db()
    with _write_lock:
        db.execute("""
            INSERT OR IGNORE INTO dismissed_teardowns (instance_id, dismissed_at)
            VALUES (?, ?)
        """, (instance_id, datetime.now(timezone.utc).isoformat()))
        db.commit()


# ── Migration from JSON state file ────────────────────────────────────

def migrate_from_json(json_path: Path):
    """One-time migration from .orchestrator-state.json to SQLite."""
    if not json_path.exists():
        return

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        count = 0
        for instance_id, dep in data.items():
            dep["instanceId"] = instance_id
            save_deployment(instance_id, {
                "name": dep.get("name", ""),
                "runtimeStatus": dep.get("runtimeStatus", "Unknown"),
                "createdTime": dep.get("createdTime", ""),
                "lastUpdatedTime": dep.get("lastUpdatedTime", ""),
                "customStatus": dep.get("customStatus", {}),
                "output": dep.get("output"),
            })
            count += 1

        # Rename old file to .bak
        bak_path = json_path.with_suffix(".json.bak")
        json_path.rename(bak_path)
        logger.info("Migrated %d deployments from JSON to SQLite (backup: %s)", count, bak_path)
    except Exception as e:
        logger.warning("JSON migration failed: %s", e)


# ── Run History & Form History Reconciliation from Storage ─────────────

def _extract_form_history_pairs(custom_status: dict[str, Any], config: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    cfg = dict(config or {})
    if isinstance(custom_status.get("deployConfig"), dict):
        cfg.update(custom_status["deployConfig"])

    pairs: list[tuple[str, str]] = []
    ws = str(cfg.get("fabric_workspace_name") or custom_status.get("workspaceName") or "").strip()
    rg = str(cfg.get("resource_group_name") or custom_status.get("resourceGroupName") or "").strip()
    if ws:
        pairs.append(("fabric-workspace", ws))
        if not rg or rg == f"rg-{ws}":
            pairs.append(("naming-prefix", ws))
    if rg:
        pairs.append(("resource-group", rg))

    scalar_fields = (
        ("location", cfg.get("location")),
        ("admin-security-group", cfg.get("admin_security_group")),
        ("alert-email", cfg.get("alert_email")),
        ("payer-ops-email", cfg.get("payer_ops_email")),
        ("databricks-environment", cfg.get("databricks_environment") if cfg.get("deploy_databricks") else ""),
        ("admin-security-group", cfg.get("databricks_admin_group")),
        ("cardiology-location", cfg.get("cardiology_location") if cfg.get("deploy_cardiology") else ""),
        ("cardiology-prefix", cfg.get("cardiology_prefix")),
        ("cardiology-chat-model", cfg.get("cardiology_chat_model")),
        ("cardiology-chat-model-version", cfg.get("cardiology_chat_model_version")),
    )
    for field, raw_val in scalar_fields:
        val = str(raw_val or "").strip()
        if val:
            pairs.append((field, val))

    for field, list_key in (
        ("cardiology-app-users", "cardiology_app_users"),
        ("cardiology-reviewer-users", "cardiology_reviewer_users"),
    ):
        items = cfg.get(list_key)
        if isinstance(items, list):
            for item in items:
                val = str(item or "").strip()
                if val:
                    pairs.append((field, val))

    tags = cfg.get("tags")
    if isinstance(tags, dict) and tags:
        clean_tags = {str(k).strip(): str(v).strip() for k, v in tags.items() if str(k).strip()}
        if clean_tags:
            pairs.append(("tags", json.dumps(clean_tags, sort_keys=True)))

    tid = str(cfg.get("expected_tenant_id") or "").strip().lower()
    sub = str(cfg.get("expected_subscription_id") or custom_status.get("subscriptionId") or "").strip().lower()
    if tid and sub:
        pairs.append(("deployment-auth-target", json.dumps({"subscription_id": sub, "tenant_id": tid}, sort_keys=True)))

    return pairs


def record_deployment_form_history(deployment: dict[str, Any]) -> int:
    """Persist form_history entries from a deployment's deployConfig / customStatus."""
    custom_status = deployment.get("customStatus")
    if not isinstance(custom_status, dict):
        return 0
    if custom_status.get("runType") in {"teardown", "teardownBatch"} or deployment.get("name") == "teardown_orchestrator":
        return 0
    used_at = str(deployment.get("lastUpdatedTime") or deployment.get("createdTime") or datetime.now(timezone.utc).isoformat())
    pairs = _extract_form_history_pairs(custom_status, deployment.get("config") if isinstance(deployment.get("config"), dict) else None)
    if not pairs:
        return 0
    db = get_db()
    added = 0
    with _write_lock:
        for field, value in pairs:
            existing = db.execute(
                "SELECT used_at FROM form_history WHERE field = ? AND value = ?",
                (field, value),
            ).fetchone()
            if existing and str(existing["used_at"] or "") >= used_at:
                continue
            db.execute(
                "INSERT OR REPLACE INTO form_history (field, value, used_at) VALUES (?, ?, ?)",
                (field, value, used_at),
            )
            added += 1
        if added:
            db.commit()
    return added


def backfill_form_history_from_deployments() -> int:
    """Ensure every persisted deployment's config inputs are present in form_history."""
    total = 0
    # Process oldest to newest so newer runs win used_at ordering
    for dep in reversed(list_deployments()):
        total += record_deployment_form_history(dep)
    return total


def reconcile_from_state_tracking_dir(
    tracking_dir: Path,
    default_tenant_id: str = "",
    default_subscription_id: str = "",
) -> list[dict[str, Any]]:
    """Reconstruct missing deployment history records from .deployment-state-*.json ledgers."""
    if not tracking_dir.is_dir():
        return []

    existing = list_deployments()
    known_workspaces = {
        str((dep.get("customStatus") or {}).get("workspaceName") or "").strip().casefold()
        for dep in existing
        if (dep.get("customStatus") or {}).get("runType") not in {"teardown", "teardownBatch"}
    }
    known_workspaces.discard("")

    if not default_tenant_id or not default_subscription_id:
        target_hist = get_form_history("deployment-auth-target", limit=1)
        if target_hist:
            try:
                parsed = json.loads(target_hist[0])
                default_tenant_id = default_tenant_id or str(parsed.get("tenant_id") or "")
                default_subscription_id = default_subscription_id or str(parsed.get("subscription_id") or "")
            except Exception:
                pass

    reconstructed: list[dict[str, Any]] = []
    for state_file in sorted(tracking_dir.glob(".deployment-state-*.json")):
        ws_from_name = state_file.name[len(".deployment-state-"):-len(".json")].strip()
        if not ws_from_name or ws_from_name.casefold() in known_workspaces:
            continue
        try:
            ledger = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        phase_entries = ledger.get("phases") if isinstance(ledger, dict) else None
        if not isinstance(phase_entries, list) or not phase_entries:
            continue

        last_entry = phase_entries[-1] if isinstance(phase_entries[-1], dict) else {}
        resources: dict[str, Any] = {}
        merged_steps: list[dict[str, Any]] = []
        seen_steps: dict[str, int] = {}
        first_ts = ""
        last_ts = ""
        for entry in phase_entries:
            if not isinstance(entry, dict):
                continue
            ts = str(entry.get("timestamp") or "").strip()
            if ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts
            if isinstance(entry.get("resources"), dict):
                resources.update({k: v for k, v in entry["resources"].items() if v})
            for step in entry.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                name = str(step.get("name") or "").strip()
                if not name:
                    continue
                status = "succeeded" if step.get("success") else "failed"
                phase_obj = {
                    "phase": name,
                    "status": status,
                    "duration": step.get("duration") or "",
                    "detail": step.get("detail") or "",
                    "reconciledFrom": "state-tracking",
                    "reconciledAt": ts,
                }
                key = name.casefold()
                if key in seen_steps:
                    merged_steps[seen_steps[key]] = phase_obj
                else:
                    seen_steps[key] = len(merged_steps)
                    merged_steps.append(phase_obj)

        if not merged_steps:
            continue

        ws_name = str(resources.get("FabricWorkspaceName") or ws_from_name).strip()
        rg_name = str(resources.get("ResourceGroupName") or f"rg-{ws_name}").strip()
        location = str(resources.get("Location") or "westus2").strip()
        succeeded = str(last_entry.get("phase") or "") != "Failed" and all(
            s.get("status") == "succeeded" for s in merged_steps
        )
        runtime_status = "Completed" if succeeded else "Failed"
        status_label = "succeeded" if succeeded else "failed"
        created_iso = first_ts or last_ts or datetime.now(timezone.utc).isoformat()
        updated_iso = last_ts or created_iso
        ts_compact = "".join(c for c in created_iso[:19] if c.isdigit())[:14]
        if len(ts_compact) == 14:
            ts_slug = f"{ts_compact[:8]}-{ts_compact[8:]}"
        else:
            ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        instance_id = f"P1234567-{ts_slug}-{ws_name}"

        deploy_config = {
            "expected_tenant_id": default_tenant_id,
            "expected_subscription_id": default_subscription_id,
            "resource_group_name": rg_name,
            "location": location,
            "fabric_workspace_name": ws_name,
            "patient_count": 100,
        }
        dep_record = {
            "instanceId": instance_id,
            "name": "deploy_all_orchestrator",
            "runtimeStatus": runtime_status,
            "createdTime": created_iso,
            "lastUpdatedTime": updated_iso,
            "customStatus": {
                "currentPhase": "Deployment Complete" if succeeded else merged_steps[-1]["phase"],
                "status": status_label,
                "detail": "Reconstructed from state-tracking ledger",
                "completedPhases": sum(1 for s in merged_steps if s.get("status") == "succeeded"),
                "totalPhases": max(16, len(merged_steps)),
                "resources": resources,
                "logs": [],
                "subStepsByPhase": {},
                "workspaceName": ws_name,
                "resourceGroupName": rg_name,
                "links": {
                    "azurePortal": f"https://portal.azure.com/#@/resource/subscriptions/{default_subscription_id}/resourceGroups/{rg_name}" if rg_name else "",
                    "fabricWorkspace": f"https://app.fabric.microsoft.com/groups?experience=fabric-developer&name={ws_name}" if ws_name else "",
                },
                "deployConfig": deploy_config,
                "reconciledFrom": "state-tracking",
            },
            "output": {
                "status": status_label,
                "phases": merged_steps,
                "resources": {"fabric_workspace_name": ws_name, "resource_group_name": rg_name, **resources},
            },
            "config": deploy_config,
        }
        save_deployment(instance_id, dep_record)
        record_deployment_form_history(dep_record)
        known_workspaces.add(ws_name.casefold())
        reconstructed.append(dep_record)
        logger.info("Reconstructed deployment %s for workspace '%s' from %s", instance_id, ws_name, state_file)

    return reconstructed


def _deployment_matches_target(
    dep: dict[str, Any],
    tenant_id: str,
    subscription_id: str,
    peer_has_matching_target: bool = False,
) -> bool:
    cs = dep.get("customStatus") or {}
    cfg = cs.get("deployConfig") or dep.get("config") or {}
    dep_tid = str(cfg.get("expected_tenant_id") or "").strip().lower()
    dep_sub = str(
        cfg.get("expected_subscription_id")
        or cs.get("subscriptionId")
        or cs.get("capacitySubscriptionId")
        or ""
    ).strip().lower()
    tid_norm = tenant_id.strip().lower()
    sub_norm = subscription_id.strip().lower()
    if dep_sub and sub_norm and dep_sub == sub_norm:
        return not (dep_tid and tid_norm and dep_tid != tid_norm)
    if dep_tid and tid_norm and dep_tid == tid_norm and not dep_sub:
        return True
    if not dep_tid and not dep_sub and peer_has_matching_target:
        return True
    return False


def import_target_history_from_shared_storage(
    tenant_id: str,
    subscription_id: str,
    shared_root: Path | None = None,
    active_data_dir: Path | None = None,
) -> dict[str, int]:
    """Import prior runs, state-tracking ledgers, and form_history for a verified (tenant_id, subscription_id) from peer sandbox directories."""
    tid = (tenant_id or "").strip().lower()
    sub = (subscription_id or "").strip().lower()
    if not tid and not sub:
        return {"importedDeployments": 0, "importedFormHistory": 0, "reconstructedLedgers": 0}

    root = shared_root or (Path(os.environ["HLS_SHARED_DATA_DIR"]) if os.environ.get("HLS_SHARED_DATA_DIR") else None)
    current_dir = active_data_dir or (Path(_persistent_dir) if _persistent_dir else None)
    if root is None or not root.is_dir():
        return {"importedDeployments": 0, "importedFormHistory": 0, "reconstructedLedgers": 0}

    imported_deployments = 0
    imported_history = 0
    reconstructed_ledgers = 0
    existing_by_id = {d["instanceId"]: d for d in list_deployments()}

    for peer_dir in sorted(root.iterdir()):
        if not peer_dir.is_dir():
            continue
        try:
            if current_dir and peer_dir.resolve() == current_dir.resolve():
                continue
        except Exception:
            if current_dir and peer_dir.name == current_dir.name:
                continue

        peer_db_path = peer_dir / "orchestrator.db"
        peer_matches_target = False
        peer_deps: list[dict[str, Any]] = []
        peer_fh: list[tuple[str, str, str]] = []

        if peer_db_path.is_file():
            temp_copy = Path(tempfile.mktemp(prefix="hls-peer-", suffix=".db"))
            try:
                shutil.copyfile(peer_db_path, temp_copy)
                with closing(sqlite3.connect(str(temp_copy), timeout=10)) as peer_conn:
                    peer_conn.row_factory = sqlite3.Row
                    fh_rows = peer_conn.execute(
                        "SELECT field, value, used_at FROM form_history ORDER BY used_at ASC"
                    ).fetchall()
                    for r in fh_rows:
                        field_name = str(r["field"] or "")
                        val_str = str(r["value"] or "")
                        used_at = str(r["used_at"] or "")
                        peer_fh.append((field_name, val_str, used_at))
                        if field_name == "deployment-auth-target":
                            try:
                                parsed = json.loads(val_str)
                                p_tid = str(parsed.get("tenant_id") or "").strip().lower()
                                p_sub = str(parsed.get("subscription_id") or "").strip().lower()
                                if (sub and p_sub == sub) and (not tid or not p_tid or p_tid == tid):
                                    peer_matches_target = True
                            except Exception:
                                pass

                    dep_rows = peer_conn.execute(
                        "SELECT * FROM deployments ORDER BY created_time ASC"
                    ).fetchall()
                    for r in dep_rows:
                        dep = _row_to_deployment(r)
                        peer_deps.append(dep)
                        if _deployment_matches_target(dep, tid, sub, False):
                            peer_matches_target = True
            except Exception as exc:
                logger.warning("Failed to inspect peer database %s: %s", peer_db_path, exc)
            finally:
                temp_copy.unlink(missing_ok=True)

        if not peer_matches_target:
            continue

        # 1. Import matching deployments from peer SQLite DB
        for dep in peer_deps:
            if not _deployment_matches_target(dep, tid, sub, peer_matches_target):
                continue
            inst_id = dep["instanceId"]
            local_dep = existing_by_id.get(inst_id)
            if local_dep:
                local_updated = str(local_dep.get("lastUpdatedTime") or "")
                peer_updated = str(dep.get("lastUpdatedTime") or "")
                if peer_updated <= local_updated:
                    continue
            save_deployment(inst_id, dep)
            record_deployment_form_history(dep)
            existing_by_id[inst_id] = dep
            imported_deployments += 1

            # Copy per-deployment log file and state-tracking ledger if present
            if current_dir:
                peer_log = peer_dir / "logs" / f"{inst_id}.jsonl"
                local_log = current_dir / "logs" / f"{inst_id}.jsonl"
                if peer_log.is_file() and not local_log.exists():
                    local_log.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(peer_log, local_log)

        # 2. Copy and reconcile peer state-tracking ledgers
        peer_tracking = peer_dir / "state-tracking"
        if peer_tracking.is_dir():
            if current_dir:
                local_tracking = current_dir / "state-tracking"
                local_tracking.mkdir(parents=True, exist_ok=True)
                for ledger_file in peer_tracking.glob(".deployment-state-*.json"):
                    target_ledger = local_tracking / ledger_file.name
                    if not target_ledger.exists():
                        shutil.copyfile(ledger_file, target_ledger)
                rec = reconcile_from_state_tracking_dir(local_tracking, tid, sub)
            else:
                rec = reconcile_from_state_tracking_dir(peer_tracking, tid, sub)
            reconstructed_ledgers += len(rec)

        # 3. Import form_history entries from matching peer sandbox
        db = get_db()
        with _write_lock:
            for field_name, val_str, used_at in peer_fh:
                if not val_str.strip():
                    continue
                existing_fh = db.execute(
                    "SELECT used_at FROM form_history WHERE field = ? AND value = ?",
                    (field_name, val_str),
                ).fetchone()
                if existing_fh and str(existing_fh["used_at"] or "") >= used_at:
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO form_history (field, value, used_at) VALUES (?, ?, ?)",
                    (field_name, val_str, used_at or datetime.now(timezone.utc).isoformat()),
                )
                imported_history += 1
            if imported_history:
                db.commit()

    return {
        "importedDeployments": imported_deployments,
        "importedFormHistory": imported_history,
        "reconstructedLedgers": reconstructed_ledgers,
    }
