"""
Keeps the local `instances` table in sync with EC2.

- reconcile_instances()        : walk stored instances, grouped by the AWS
                                 credential that owns them and by region, and
                                 refresh state/IPs. Runs on demand
                                 (POST /api/instances/reconcile) and on a
                                 timer from main.py (RECONCILE_INTERVAL_SECONDS).
- sync_deployment_instances()  : after a GitHub Actions deploy, discover the
                                 new instances via their PortalDeploymentId tag.
- wait_for_stable_state()      : after start/stop/reboot, poll until the
                                 instance settles and record its new public IP
                                 (EC2 assigns a fresh one on every start).
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from database.db import (
    get_credential,
    get_instance,
    list_instances,
    mark_instance_missing,
    save_instance,
    update_instance_network,
)
from services.aws_clients import session_for_credential
from services.prometheus_targets import rewrite_targets

logger = logging.getLogger(__name__)

# EC2 lifecycle state -> portal state. Transitional states are kept so the UI
# can show "pending"/"stopping" while an action is in flight.
EC2_STATE_MAP = {
    "pending": "pending",
    "running": "running",
    "stopping": "stopping",
    "stopped": "stopped",
    "shutting-down": "terminated",
    "terminated": "terminated",
}
STABLE_STATES = {"running", "stopped", "terminated"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tags_dict(ec2_instance: dict) -> dict:
    return {t["Key"]: t["Value"] for t in ec2_instance.get("Tags", [])}


def _describe(credential: Optional[dict], region: str, **kwargs) -> List[dict]:
    """Synchronous describe_instances returning a flat list of instances."""
    client = session_for_credential(credential, region).client("ec2")
    found: List[dict] = []
    for page in client.get_paginator("describe_instances").paginate(**kwargs):
        for reservation in page.get("Reservations", []):
            found.extend(reservation.get("Instances", []))
    return found


def _describe_ids(credential: Optional[dict], region: str, ids: List[str]) -> Dict[str, dict]:
    """
    describe_instances for known ids. Ids AWS no longer knows about make the
    whole call fail, so fall back to one-by-one to isolate them.
    """
    try:
        return {i["InstanceId"]: i for i in _describe(credential, region, InstanceIds=ids)}
    except Exception as exc:
        if "InvalidInstanceID" not in str(exc):
            raise
        if len(ids) == 1:
            return {}
    result: Dict[str, dict] = {}
    for instance_id in ids:
        result.update(_describe_ids(credential, region, [instance_id]))
    return result


def _apply_ec2_snapshot(row: dict, ec2: dict) -> Tuple[str, str]:
    """Persist state/IPs/tags from an EC2 description. Returns (old, new) state."""
    previous = row.get("state", "unknown")
    latest = EC2_STATE_MAP.get(ec2.get("State", {}).get("Name", ""), previous)
    refreshed = dict(row)
    refreshed.update(
        {
            "state": latest,
            "public_ip": ec2.get("PublicIpAddress"),
            "private_ip": ec2.get("PrivateIpAddress") or row.get("private_ip"),
            "tags": _tags_dict(ec2),
        }
    )
    save_instance(refreshed)
    return previous, latest


async def reconcile_instances(
    instance_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
) -> dict:
    """
    Reconcile stored instances with AWS. `user_id` limits the scope to one
    user (API calls); None reconciles everyone (background loop).
    """
    if instance_ids:
        candidates = [get_instance(i, user_id) for i in instance_ids]
        instances = [inst for inst in candidates if inst is not None]
    else:
        instances = list_instances(user_id=user_id, exclude_terminated=True)

    started_at = _now()
    # Group by (credential, region): each group is one describe call.
    grouped: Dict[Tuple[Optional[str], str], List[dict]] = defaultdict(list)
    for inst in instances:
        grouped[(inst.get("credential_id"), inst.get("region") or "us-east-1")].append(inst)

    transitions = []
    errors = []
    for (credential_id, region), rows in grouped.items():
        credential = get_credential(credential_id) if credential_id else None
        try:
            described = await asyncio.to_thread(
                _describe_ids, credential, region, [r["id"] for r in rows]
            )
        except Exception as exc:
            errors.append({"region": region, "error": str(exc)})
            continue
        for row in rows:
            ec2 = described.get(row["id"])
            if ec2 is None:
                previous, latest = row.get("state", "unknown"), "terminated"
                mark_instance_missing(row["id"])
            else:
                previous, latest = _apply_ec2_snapshot(row, ec2)
            if previous != latest:
                transitions.append({"instance_id": row["id"], "from": previous, "to": latest})

    rewrite_targets()
    return {
        "checked": len(instances),
        "updated": len(transitions),
        "transitions": transitions,
        "errors": errors,
        "started_at": started_at,
        "finished_at": _now(),
    }


async def sync_deployment_instances(
    deployment_id: str,
    request,
    credential: Optional[dict],
) -> List[dict]:
    """Record instances created by a (remote) deployment, found by tag."""
    described = await asyncio.to_thread(
        _describe,
        credential,
        request.region,
        Filters=[
            {"Name": "tag:PortalDeploymentId", "Values": [deployment_id]},
            {"Name": "instance-state-name", "Values": ["pending", "running"]},
        ],
    )
    ssh_user = "ubuntu" if request.os_type == "ubuntu" else "ec2-user"
    saved = []
    for ec2 in described:
        row = {
            "id": ec2["InstanceId"],
            "deployment_id": deployment_id,
            "public_ip": ec2.get("PublicIpAddress"),
            "private_ip": ec2.get("PrivateIpAddress"),
            "ssh_user": ssh_user,
            "key_pair_name": request.key_pair_name,
            "os_type": request.os_type,
            "region": request.region,
            "instance_type": ec2.get("InstanceType", request.instance_type),
            "state": EC2_STATE_MAP.get(ec2.get("State", {}).get("Name", ""), "running"),
            "tags": _tags_dict(ec2),
        }
        save_instance(row)
        saved.append(row)
    rewrite_targets()
    return saved


async def wait_for_stable_state(instance_id: str, timeout_seconds: int = 300) -> None:
    """Poll one instance until it reaches a stable state, then persist it."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        await asyncio.sleep(5)
        row = get_instance(instance_id)
        if not row:
            return
        credential = get_credential(row["credential_id"]) if row.get("credential_id") else None
        try:
            described = await asyncio.to_thread(
                _describe_ids, credential, row.get("region") or "us-east-1", [instance_id]
            )
        except Exception:
            logger.exception("Polling %s failed", instance_id)
            continue
        ec2 = described.get(instance_id)
        if ec2 is None:
            mark_instance_missing(instance_id)
            break
        state = EC2_STATE_MAP.get(ec2.get("State", {}).get("Name", ""), "unknown")
        update_instance_network(
            instance_id, state, ec2.get("PublicIpAddress"), ec2.get("PrivateIpAddress")
        )
        if state in STABLE_STATES:
            break
    rewrite_targets()
