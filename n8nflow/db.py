"""SQLite persistence for workflows, executions, credentials."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os

from .crypto import decrypt_text, encrypt_text

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("N8NFLOW_DB", DATA_DIR / "n8nflow.db"))

_LOCAL = threading.local()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def _connect() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _LOCAL.conn = conn
    return conn


@contextmanager
def cursor():
    conn = _connect()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_db() -> None:
    with cursor() as cur:
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER DEFAULT 0,
                nodes TEXT NOT NULL,
                connections TEXT NOT NULL,
                settings TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                created_at TEXT,
                updated_at TEXT,
                last_run_at TEXT
            );
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                workflow_name TEXT,
                status TEXT,
                mode TEXT,
                started_at TEXT,
                finished_at TEXT,
                data TEXT,
                error TEXT,
                trigger_data TEXT
            );
            CREATE TABLE IF NOT EXISTS credentials (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS webhook_inbox (
                id TEXT PRIMARY KEY,
                token TEXT,
                workflow_id TEXT,
                received_at TEXT,
                payload TEXT,
                meta TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_exec_started ON executions(started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_exec_wf ON executions(workflow_id);
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def get_setting(key: str, default: str | None = None) -> str | None:
    with cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ---------- workflows ----------

def _decode_wf(row: sqlite3.Row | dict) -> dict[str, Any]:
    d = dict(row)
    d["active"] = bool(d.get("active"))
    d["nodes"] = json.loads(d.get("nodes") or "[]")
    d["connections"] = json.loads(d.get("connections") or "{}")
    d["settings"] = json.loads(d.get("settings") or "{}")
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def list_workflows() -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM workflows ORDER BY updated_at DESC")
        rows = cur.fetchall()
    return [_decode_wf(r) for r in rows]


def get_workflow(wf_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM workflows WHERE id=?", (wf_id,))
        row = cur.fetchone()
    return _decode_wf(row) if row else None


def save_workflow(wf: dict[str, Any], *, create: bool = False) -> dict[str, Any]:
    now = utcnow()
    wf = dict(wf)
    wf.setdefault("id", new_id())
    wf.setdefault("created_at", now)
    wf["updated_at"] = now
    wf.setdefault("active", False)
    wf.setdefault("nodes", [])
    wf.setdefault("connections", {})
    wf.setdefault("settings", {})
    wf.setdefault("tags", [])
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflows(id, name, active, nodes, connections, settings, tags, created_at, updated_at, last_run_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                active=excluded.active,
                nodes=excluded.nodes,
                connections=excluded.connections,
                settings=excluded.settings,
                tags=excluded.tags,
                updated_at=excluded.updated_at,
                last_run_at=COALESCE(excluded.last_run_at, workflows.last_run_at)
            """,
            (
                wf["id"],
                wf.get("name") or "Untitled",
                1 if wf.get("active") else 0,
                json.dumps(wf["nodes"], ensure_ascii=False),
                json.dumps(wf["connections"], ensure_ascii=False),
                json.dumps(wf.get("settings") or {}, ensure_ascii=False),
                json.dumps(wf.get("tags") or [], ensure_ascii=False),
                wf.get("created_at") or now,
                now,
                wf.get("last_run_at"),
            ),
        )
    return get_workflow(wf["id"])  # type: ignore[return-value]


def touch_workflow_run(wf_id: str) -> None:
    with cursor() as cur:
        cur.execute(
            "UPDATE workflows SET last_run_at=? WHERE id=?",
            (utcnow(), wf_id),
        )


def delete_workflow(wf_id: str) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM workflows WHERE id=?", (wf_id,))


def set_workflow_active(wf_id: str, active: bool) -> None:
    with cursor() as cur:
        cur.execute(
            "UPDATE workflows SET active=?, updated_at=? WHERE id=?",
            (1 if active else 0, utcnow(), wf_id),
        )


def duplicate_workflow(wf_id: str) -> dict[str, Any] | None:
    wf = get_workflow(wf_id)
    if not wf:
        return None
    wf["id"] = new_id()
    wf["name"] = f"{wf['name']} copy"
    wf["active"] = False
    wf["created_at"] = utcnow()
    wf["last_run_at"] = None
    return save_workflow(wf, create=True)


# ---------- executions ----------

def insert_execution(ex: dict[str, Any]) -> dict[str, Any]:
    ex = dict(ex)
    ex.setdefault("id", new_id())
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO executions(id, workflow_id, workflow_name, status, mode, started_at, finished_at, data, error, trigger_data)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ex["id"],
                ex.get("workflow_id"),
                ex.get("workflow_name"),
                ex.get("status") or "running",
                ex.get("mode") or "manual",
                ex.get("started_at") or utcnow(),
                ex.get("finished_at"),
                json.dumps(ex.get("data"), ensure_ascii=False) if ex.get("data") is not None else None,
                ex.get("error"),
                json.dumps(ex.get("trigger_data"), ensure_ascii=False)
                if ex.get("trigger_data") is not None
                else None,
            ),
        )
    return ex


def finish_execution(ex_id: str, *, status: str, data: Any, error: str | None, finished_at: str | None = None) -> None:
    with cursor() as cur:
        cur.execute(
            "UPDATE executions SET status=?, finished_at=?, data=?, error=? WHERE id=?",
            (
                status,
                finished_at or utcnow(),
                json.dumps(data, ensure_ascii=False) if data is not None else None,
                error,
                ex_id,
            ),
        )


def list_executions(limit: int = 80, workflow_id: str | None = None) -> list[dict[str, Any]]:
    with cursor() as cur:
        if workflow_id:
            cur.execute(
                "SELECT * FROM executions WHERE workflow_id=? ORDER BY started_at DESC LIMIT ?",
                (workflow_id, limit),
            )
        else:
            cur.execute("SELECT * FROM executions ORDER BY started_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("data"):
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                pass
        if d.get("trigger_data"):
            try:
                d["trigger_data"] = json.loads(d["trigger_data"])
            except Exception:
                pass
        out.append(d)
    return out


def get_execution(ex_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM executions WHERE id=?", (ex_id,))
        row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("data", "trigger_data"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    return d


def execution_stats() -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM workflows")
        total_wf = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM workflows WHERE active=1")
        active_wf = cur.fetchone()["c"]
        cur.execute(
            """
            SELECT COUNT(*) AS c FROM executions
            WHERE started_at >= date('now')
            """
        )
        today = cur.fetchone()["c"]
        cur.execute("SELECT status, COUNT(*) AS c FROM executions GROUP BY status")
        by_status = {r["status"]: r["c"] for r in cur.fetchall()}
    success = by_status.get("success", 0)
    error = by_status.get("error", 0)
    denom = success + error
    rate = round(100 * success / denom, 1) if denom else 0.0
    return {
        "workflows": total_wf,
        "active": active_wf,
        "today": today,
        "success_rate": rate,
        "success": success,
        "error": error,
        "total_exec": success + error + by_status.get("running", 0),
    }


# ---------- credentials ----------

def list_credentials() -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT id, name, type, created_at FROM credentials ORDER BY name")
        return [dict(r) for r in cur.fetchall()]


def get_credential(cid: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM credentials WHERE id=?", (cid,))
        row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["data"] = json.loads(decrypt_text(d["data"]))
    return d


def save_credential(name: str, cred_type: str, data: dict[str, Any], cid: str | None = None) -> str:
    cid = cid or new_id()
    blob = encrypt_text(json.dumps(data, ensure_ascii=False))
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO credentials(id, name, type, data, created_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, type=excluded.type, data=excluded.data
            """,
            (cid, name, cred_type, blob, utcnow()),
        )
    return cid


def delete_credential(cid: str) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM credentials WHERE id=?", (cid,))


# ---------- webhook inbox ----------

def log_webhook(token: str, workflow_id: str, payload: Any, meta: Any = None) -> str:
    wid = new_id()
    with cursor() as cur:
        cur.execute(
            "INSERT INTO webhook_inbox(id, token, workflow_id, received_at, payload, meta) VALUES(?,?,?,?,?,?)",
            (
                wid,
                token,
                workflow_id,
                utcnow(),
                json.dumps(payload, ensure_ascii=False),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
    return wid


def list_webhook_inbox(limit: int = 50) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM webhook_inbox ORDER BY received_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for key in ("payload", "meta"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except Exception:
                    pass
        out.append(d)
    return out


# ---------- backup ----------

def export_backup() -> dict[str, Any]:
    wfs = list_workflows()
    creds = []
    with cursor() as cur:
        cur.execute("SELECT * FROM credentials")
        for r in cur.fetchall():
            item = dict(r)
            try:
                item["data"] = json.loads(decrypt_text(item["data"]))
            except Exception:
                item["data"] = {"_error": "undecryptable"}
            creds.append(item)
        cur.execute("SELECT * FROM settings")
        settings = {r["key"]: r["value"] for r in cur.fetchall()}
    return {
        "format": "n8nflow-backup",
        "version": 1,
        "exported_at": utcnow(),
        "workflows": wfs,
        "credentials": creds,
        "settings": settings,
    }


def import_backup(payload: dict[str, Any], *, replace: bool = False) -> dict[str, int]:
    if replace:
        with cursor() as cur:
            cur.execute("DELETE FROM workflows")
            cur.execute("DELETE FROM credentials")
    w_count = 0
    c_count = 0
    for wf in payload.get("workflows") or []:
        if not wf.get("id"):
            wf["id"] = new_id()
        save_workflow(wf)
        w_count += 1
    for cred in payload.get("credentials") or []:
        if cred.get("data") == {"_error": "undecryptable"}:
            continue
        save_credential(
            cred.get("name") or "imported",
            cred.get("type") or "generic",
            cred.get("data") or {},
            cid=cred.get("id"),
        )
        c_count += 1
    for k, v in (payload.get("settings") or {}).items():
        if k:
            set_setting(k, str(v))
    return {"workflows": w_count, "credentials": c_count}


def reset_all() -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM workflows")
        cur.execute("DELETE FROM executions")
        cur.execute("DELETE FROM credentials")
        cur.execute("DELETE FROM webhook_inbox")
        cur.execute("DELETE FROM settings")
