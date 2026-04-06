"""
SQLite-backed deployment history using the stdlib sqlite3 module.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

DB_PATH = os.getenv("DB_PATH", "deployments.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                id           TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'pending',
                provider     TEXT,
                region       TEXT,
                instance_type TEXT,
                instances    INTEGER,
                config       TEXT,
                logs         TEXT DEFAULT '[]',
                created_at   TEXT,
                updated_at   TEXT
            )
        """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_deployment(deployment_id: str, request_data: dict) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO deployments
              (id, status, provider, region, instance_type, instances,
               config, logs, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deployment_id,
                "pending",
                request_data.get("provider", "aws"),
                request_data.get("region", ""),
                request_data.get("instance_type", ""),
                request_data.get("instances", 1),
                json.dumps(request_data),
                "[]",
                now,
                now,
            ),
        )


def update_deployment_status(
    deployment_id: str,
    status: str,
    logs: Optional[List[str]] = None,
) -> None:
    now = _now()
    with _conn() as con:
        if logs is not None:
            con.execute(
                "UPDATE deployments SET status=?, logs=?, updated_at=? WHERE id=?",
                (status, json.dumps(logs), now, deployment_id),
            )
        else:
            con.execute(
                "UPDATE deployments SET status=?, updated_at=? WHERE id=?",
                (status, now, deployment_id),
            )


def get_all_deployments() -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM deployments ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


def get_deployment(deployment_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM deployments WHERE id=?", (deployment_id,)
        ).fetchone()
    return dict(row) if row else None
