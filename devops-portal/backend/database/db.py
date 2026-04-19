"""
SQLite-backed deployment history using the stdlib sqlite3 module.

Tables:
  deployments              - one row per portal deployment request
  instances                - one row per EC2 instance produced by a deployment
  instance_configurations  - one row per day-2 package/config job against an instance
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
                execution_mode TEXT NOT NULL DEFAULT 'local',
                external_ref TEXT,
                external_url TEXT,
                config       TEXT,
                logs         TEXT DEFAULT '[]',
                created_at   TEXT,
                updated_at   TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS instances (
                id             TEXT PRIMARY KEY,
                deployment_id  TEXT NOT NULL,
                public_ip      TEXT,
                private_ip     TEXT,
                ssh_user       TEXT,
                key_pair_name  TEXT,
                os_type        TEXT,
                region         TEXT,
                instance_type  TEXT,
                state          TEXT NOT NULL DEFAULT 'running',
                tags           TEXT DEFAULT '{}',
                created_at     TEXT,
                updated_at     TEXT,
                last_seen_at   TEXT,
                FOREIGN KEY (deployment_id) REFERENCES deployments(id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS instance_configurations (
                id               TEXT PRIMARY KEY,
                instance_id      TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'pending',
                packages         TEXT DEFAULT '[]',
                custom_commands  TEXT DEFAULT '',
                logs             TEXT DEFAULT '[]',
                created_at       TEXT,
                updated_at       TEXT,
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            )
        """)
        _ensure_columns(con)


def _ensure_columns(con: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in con.execute("PRAGMA table_info(deployments)").fetchall()
    }
    migrations = {
        "execution_mode": (
            "ALTER TABLE deployments ADD COLUMN execution_mode TEXT "
            "NOT NULL DEFAULT 'local'"
        ),
        "external_ref": "ALTER TABLE deployments ADD COLUMN external_ref TEXT",
        "external_url": "ALTER TABLE deployments ADD COLUMN external_url TEXT",
    }
    for column_name, statement in migrations.items():
        if column_name not in columns:
            con.execute(statement)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_deployment(
    deployment_id: str,
    request_data: dict,
    execution_mode: str = "local",
) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO deployments
              (id, status, provider, region, instance_type, instances, execution_mode,
               config, logs, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deployment_id,
                "pending",
                request_data.get("provider", "aws"),
                request_data.get("region", ""),
                request_data.get("instance_type", ""),
                request_data.get("instances", 1),
                execution_mode,
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


def update_deployment_execution_metadata(
    deployment_id: str,
    execution_mode: Optional[str] = None,
    external_ref: Optional[str] = None,
    external_url: Optional[str] = None,
) -> None:
    now = _now()
    assignments = []
    values: list[str] = []

    if execution_mode is not None:
        assignments.append("execution_mode=?")
        values.append(execution_mode)
    if external_ref is not None:
        assignments.append("external_ref=?")
        values.append(external_ref)
    if external_url is not None:
        assignments.append("external_url=?")
        values.append(external_url)

    assignments.append("updated_at=?")
    values.append(now)
    values.append(deployment_id)

    with _conn() as con:
        con.execute(
            f"UPDATE deployments SET {', '.join(assignments)} WHERE id=?",
            values,
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


# ---------- Instances ----------


def save_instance(instance: dict) -> None:
    """
    Insert or replace an instance record. `instance` must contain an `id`
    (EC2 instance ID) and a `deployment_id`.
    """
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO instances
              (id, deployment_id, public_ip, private_ip, ssh_user, key_pair_name,
               os_type, region, instance_type, state, tags,
               created_at, updated_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              public_ip=excluded.public_ip,
              private_ip=excluded.private_ip,
              ssh_user=excluded.ssh_user,
              key_pair_name=excluded.key_pair_name,
              os_type=excluded.os_type,
              region=excluded.region,
              instance_type=excluded.instance_type,
              state=excluded.state,
              tags=excluded.tags,
              updated_at=excluded.updated_at,
              last_seen_at=excluded.last_seen_at
            """,
            (
                instance["id"],
                instance["deployment_id"],
                instance.get("public_ip"),
                instance.get("private_ip"),
                instance.get("ssh_user"),
                instance.get("key_pair_name"),
                instance.get("os_type"),
                instance.get("region"),
                instance.get("instance_type"),
                instance.get("state", "running"),
                json.dumps(instance.get("tags", {})),
                now,
                now,
                now,
            ),
        )


def save_instances(deployment_id: str, instances: List[dict]) -> None:
    for instance in instances:
        row = dict(instance)
        row["deployment_id"] = deployment_id
        save_instance(row)


def list_instances(state: Optional[str] = None) -> List[dict]:
    query = "SELECT * FROM instances"
    params: list = []
    if state:
        query += " WHERE state=?"
        params.append(state)
    query += " ORDER BY created_at DESC"
    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_instance(instance_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM instances WHERE id=?", (instance_id,)
        ).fetchone()
    return dict(row) if row else None


def update_instance_state(instance_id: str, state: str) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            "UPDATE instances SET state=?, updated_at=?, last_seen_at=? WHERE id=?",
            (state, now, now, instance_id),
        )


def mark_instance_missing(instance_id: str) -> None:
    """
    Flag an instance as terminated because AWS no longer reports it.
    last_seen_at is NOT bumped here — the gap is intentional.
    """
    now = _now()
    with _conn() as con:
        con.execute(
            "UPDATE instances SET state=?, updated_at=? WHERE id=?",
            ("terminated", now, instance_id),
        )


# ---------- Instance configurations ----------


def save_instance_configuration(
    configuration_id: str,
    instance_id: str,
    packages: List[str],
    custom_commands: str,
) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO instance_configurations
              (id, instance_id, status, packages, custom_commands,
               logs, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                configuration_id,
                instance_id,
                "pending",
                json.dumps(packages),
                custom_commands,
                "[]",
                now,
                now,
            ),
        )


def update_instance_configuration_status(
    configuration_id: str,
    status: str,
    logs: Optional[List[str]] = None,
) -> None:
    now = _now()
    with _conn() as con:
        if logs is not None:
            con.execute(
                "UPDATE instance_configurations "
                "SET status=?, logs=?, updated_at=? WHERE id=?",
                (status, json.dumps(logs), now, configuration_id),
            )
        else:
            con.execute(
                "UPDATE instance_configurations "
                "SET status=?, updated_at=? WHERE id=?",
                (status, now, configuration_id),
            )


def get_instance_configuration(configuration_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM instance_configurations WHERE id=?",
            (configuration_id,),
        ).fetchone()
    return dict(row) if row else None


def list_instance_configurations(instance_id: str) -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM instance_configurations "
            "WHERE instance_id=? ORDER BY created_at DESC LIMIT 50",
            (instance_id,),
        ).fetchall()
    return [dict(r) for r in rows]
