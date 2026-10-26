"""
SQLite-backed persistence using the stdlib sqlite3 module.

Tables:
  users                    - portal accounts (email + scrypt password hash)
  aws_credentials          - per-user AWS access keys and SSH key pairs;
                             secrets are Fernet-encrypted (services/crypto.py)
  deployments              - one row per portal deployment request
  instances                - one row per EC2 instance produced by a deployment
  instance_configurations  - one row per day-2 package/config job against an instance

Every user-facing row carries a `user_id` so that routes can scope queries to
the logged-in user. Columns added after the first release are created by
_ensure_columns(), so existing databases upgrade in place on startup.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

DB_PATH = os.getenv("DB_PATH", "deployments.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        # WAL lets the CloudWatch exporter read while the backend writes.
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id             TEXT PRIMARY KEY,
                email          TEXT NOT NULL UNIQUE,
                password_hash  TEXT NOT NULL,
                created_at     TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS aws_credentials (
                id                     TEXT PRIMARY KEY,
                user_id                TEXT NOT NULL,
                name                   TEXT NOT NULL,
                access_key_id          TEXT NOT NULL,
                secret_access_key_enc  TEXT NOT NULL,
                default_region         TEXT NOT NULL,
                account_id             TEXT,
                arn                    TEXT,
                key_pair_name          TEXT,
                ssh_public_key         TEXT,
                ssh_private_key_enc    TEXT,
                created_at             TEXT,
                updated_at             TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
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
    """Add columns introduced after a table was first created."""
    migrations = {
        "deployments": {
            "execution_mode": "TEXT NOT NULL DEFAULT 'local'",
            "external_ref": "TEXT",
            "external_url": "TEXT",
            "user_id": "TEXT",
            "credential_id": "TEXT",
        },
        "instances": {
            "user_id": "TEXT",
            "credential_id": "TEXT",
            "name": "TEXT",
        },
    }
    for table, columns in migrations.items():
        existing = {
            row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column_name, ddl in columns.items():
            if column_name not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {ddl}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Users ----------


def create_user(user_id: str, email: str, password_hash: str) -> None:
    with _conn() as con:
        is_first_user = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        con.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, password_hash, _now()),
        )
        if is_first_user:
            # Rows created before authentication existed have no owner; hand
            # them to the first account so existing history is not lost.
            con.execute("UPDATE deployments SET user_id=? WHERE user_id IS NULL", (user_id,))
            con.execute("UPDATE instances SET user_id=? WHERE user_id IS NULL", (user_id,))


def list_users_count() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user(user_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    return dict(row) if row else None


# ---------- AWS credentials ----------


def save_credential(credential: dict) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO aws_credentials
              (id, user_id, name, access_key_id, secret_access_key_enc,
               default_region, account_id, arn, key_pair_name, ssh_public_key,
               ssh_private_key_enc, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                credential["id"],
                credential["user_id"],
                credential["name"],
                credential["access_key_id"],
                credential["secret_access_key_enc"],
                credential["default_region"],
                credential.get("account_id"),
                credential.get("arn"),
                credential.get("key_pair_name"),
                credential.get("ssh_public_key"),
                credential.get("ssh_private_key_enc"),
                now,
                now,
            ),
        )


def update_credential_key_pair(
    credential_id: str,
    key_pair_name: str,
    ssh_public_key: str,
    ssh_private_key_enc: str,
) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE aws_credentials SET key_pair_name=?, ssh_public_key=?, "
            "ssh_private_key_enc=?, updated_at=? WHERE id=?",
            (key_pair_name, ssh_public_key, ssh_private_key_enc, _now(), credential_id),
        )


def list_credentials(user_id: Optional[str] = None) -> List[dict]:
    """List credentials for one user, or for everyone when user_id is None."""
    query = "SELECT * FROM aws_credentials"
    params: list = []
    if user_id is not None:
        query += " WHERE user_id=?"
        params.append(user_id)
    query += " ORDER BY created_at DESC"
    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_credential(credential_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Fetch a credential; pass user_id to enforce ownership."""
    query = "SELECT * FROM aws_credentials WHERE id=?"
    params: list = [credential_id]
    if user_id is not None:
        query += " AND user_id=?"
        params.append(user_id)
    with _conn() as con:
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


def delete_credential(credential_id: str, user_id: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM aws_credentials WHERE id=? AND user_id=?",
            (credential_id, user_id),
        )
    return cur.rowcount > 0


# ---------- Deployments ----------


def save_deployment(
    deployment_id: str,
    request_data: dict,
    execution_mode: str = "local",
    user_id: Optional[str] = None,
    credential_id: Optional[str] = None,
) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO deployments
              (id, status, provider, region, instance_type, instances, execution_mode,
               config, logs, created_at, updated_at, user_id, credential_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                user_id,
                credential_id,
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


def get_all_deployments(user_id: Optional[str] = None) -> List[dict]:
    query = "SELECT * FROM deployments"
    params: list = []
    if user_id is not None:
        query += " WHERE user_id=?"
        params.append(user_id)
    query += " ORDER BY created_at DESC LIMIT 50"
    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_deployment(deployment_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    query = "SELECT * FROM deployments WHERE id=?"
    params: list = [deployment_id]
    if user_id is not None:
        query += " AND user_id=?"
        params.append(user_id)
    with _conn() as con:
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


# ---------- Instances ----------


def save_instance(instance: dict) -> None:
    """
    Insert or replace an instance record. `instance` must contain an `id`
    (EC2 instance ID) and a `deployment_id`. Ownership columns (user_id,
    credential_id) default to the parent deployment's values when omitted.
    """
    now = _now()
    with _conn() as con:
        owner = con.execute(
            "SELECT user_id, credential_id FROM deployments WHERE id=?",
            (instance["deployment_id"],),
        ).fetchone()
        user_id = instance.get("user_id") or (owner["user_id"] if owner else None)
        credential_id = instance.get("credential_id") or (
            owner["credential_id"] if owner else None
        )
        con.execute(
            """
            INSERT INTO instances
              (id, deployment_id, public_ip, private_ip, ssh_user, key_pair_name,
               os_type, region, instance_type, state, tags,
               created_at, updated_at, last_seen_at, user_id, credential_id, name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
              last_seen_at=excluded.last_seen_at,
              user_id=COALESCE(excluded.user_id, instances.user_id),
              credential_id=COALESCE(excluded.credential_id, instances.credential_id),
              name=COALESCE(excluded.name, instances.name)
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
                user_id,
                credential_id,
                instance.get("name") or (instance.get("tags") or {}).get("Name"),
            ),
        )


def save_instances(deployment_id: str, instances: List[dict]) -> None:
    for instance in instances:
        row = dict(instance)
        row["deployment_id"] = deployment_id
        save_instance(row)


def list_instances(
    state: Optional[str] = None,
    user_id: Optional[str] = None,
    exclude_terminated: bool = False,
) -> List[dict]:
    clauses = []
    params: list = []
    if state:
        clauses.append("state=?")
        params.append(state)
    if user_id is not None:
        clauses.append("user_id=?")
        params.append(user_id)
    if exclude_terminated:
        clauses.append("state != 'terminated'")
    query = "SELECT * FROM instances"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_instance(instance_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    query = "SELECT * FROM instances WHERE id=?"
    params: list = [instance_id]
    if user_id is not None:
        query += " AND user_id=?"
        params.append(user_id)
    with _conn() as con:
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


def update_instance_state(instance_id: str, state: str) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            "UPDATE instances SET state=?, updated_at=?, last_seen_at=? WHERE id=?",
            (state, now, now, instance_id),
        )


def update_instance_network(
    instance_id: str,
    state: str,
    public_ip: Optional[str],
    private_ip: Optional[str],
) -> None:
    """Record state plus IPs - a stopped/started instance gets a new public IP."""
    now = _now()
    with _conn() as con:
        con.execute(
            "UPDATE instances SET state=?, public_ip=?, private_ip=COALESCE(?, private_ip), "
            "updated_at=?, last_seen_at=? WHERE id=?",
            (state, public_ip, private_ip, now, now, instance_id),
        )


def update_instance_tags(instance_id: str, tags: dict) -> None:
    now = _now()
    with _conn() as con:
        con.execute(
            "UPDATE instances SET tags=?, updated_at=?, last_seen_at=? WHERE id=?",
            (json.dumps(tags), now, now, instance_id),
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
