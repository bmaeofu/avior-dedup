"""Persistent run history for dedup and searchmove jobs (SQLite in /config).

Stores every started run together with its full parameters so it can be
repeated later with the same parameters (only the mode is re-selectable).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from avior_dedup import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    mode TEXT NOT NULL,
    params TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_module ON runs (module, id DESC);
"""


def _db_path() -> Path:
    return config.config_dir() / "run_history.sqlite"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def init_db() -> None:
    """Create the schema and mark orphaned 'running' runs as failed.

    The runner state lives only in memory, so any run still marked 'running'
    at server start belongs to a process that is gone.
    """
    with _connect() as conn:
        conn.execute(
            "UPDATE runs SET status='failed', finished_at=? WHERE status='running'",
            (_now(),),
        )


def record_run(module: str, mode: str, params: dict[str, Any]) -> int:
    """Insert a new run and return its id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (module, mode, params, status, created_at) VALUES (?, ?, ?, 'running', ?)",
            (module, mode, json.dumps(params, ensure_ascii=False), _now()),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, summary: dict[str, Any] | None = None) -> None:
    """Mark a run as finished with a final status and optional summary."""
    with _connect() as conn:
        conn.execute(
            "UPDATE runs SET status=?, finished_at=?, summary=? WHERE id=?",
            (
                status,
                _now(),
                json.dumps(summary, ensure_ascii=False) if summary is not None else None,
                run_id,
            ),
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "module": row["module"],
        "mode": row["mode"],
        "params": json.loads(row["params"]) if row["params"] else {},
        "status": row["status"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
        "summary": json.loads(row["summary"]) if row["summary"] else None,
    }


def list_runs(module: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """Return runs newest-first, optionally filtered by module."""
    with _connect() as conn:
        if module:
            rows = conn.execute(
                "SELECT * FROM runs WHERE module = ? ORDER BY id DESC LIMIT ?",
                (module, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_run(run_id: int) -> dict[str, Any] | None:
    """Return a single run by id, or None."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _row_to_dict(row) if row is not None else None
