"""
AWS reconciliation: walks every instance row we have stored, asks EC2 in the
instance's region whether it still exists, and updates the local state.

Runs on-demand via POST /api/instances/reconcile. No background scheduler is
wired up yet — callers trigger this explicitly.

Requires boto3. If it is not installed, reconciliation raises a clear error
rather than silently skipping.
"""

import asyncio
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database.db import (
    get_instance,
    list_instances,
    mark_instance_missing,
    save_instance,
)


EC2_STATE_MAP = {
    "pending": "running",
    "running": "running",
    "stopping": "stopped",
    "stopped": "stopped",
    "shutting-down": "terminated",
    "terminated": "terminated",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _import_boto3():
    try:
        import boto3  # noqa: F401
        return boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is not installed in the backend environment. "
            "Add `boto3` to devops-portal/backend/requirements.txt and "
            "reinstall."
        ) from exc


def _group_by_region(instances: List[dict]) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for inst in instances:
        region = inst.get("region") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        grouped[region].append(inst)
    return grouped


def _reconcile_region_sync(
    boto3_module,
    region: str,
    instances: List[dict],
    aws_access_key_id: Optional[str],
    aws_secret_access_key: Optional[str],
) -> Dict[str, str]:
    """
    Synchronous helper that calls EC2.describe_instances for the given region
    and returns {instance_id: new_state}. Runs inside asyncio.to_thread.
    """
    session_kwargs = {"region_name": region}
    if aws_access_key_id and aws_secret_access_key:
        session_kwargs["aws_access_key_id"] = aws_access_key_id
        session_kwargs["aws_secret_access_key"] = aws_secret_access_key

    client = boto3_module.client("ec2", **session_kwargs)

    ids_to_check = [inst["id"] for inst in instances]
    results: Dict[str, str] = {}

    paginator = client.get_paginator("describe_instances")
    seen: set[str] = set()
    for page in paginator.paginate(InstanceIds=ids_to_check):
        for reservation in page.get("Reservations", []):
            for ec2 in reservation.get("Instances", []):
                instance_id = ec2["InstanceId"]
                seen.add(instance_id)
                raw_state = ec2.get("State", {}).get("Name", "unknown")
                results[instance_id] = EC2_STATE_MAP.get(raw_state, raw_state)

    for inst in instances:
        if inst["id"] not in seen:
            results[inst["id"]] = "terminated"

    return results


async def reconcile_instances(
    instance_ids: Optional[List[str]] = None,
) -> dict:
    """
    Reconcile the local instances table with AWS. Pass `instance_ids` to limit
    the scope; otherwise every instance in the DB is checked.

    Returns a summary dict with counts and per-instance state transitions.
    """
    boto3_module = _import_boto3()

    if instance_ids:
        instances = [
            get_instance(instance_id)
            for instance_id in instance_ids
        ]
        instances = [inst for inst in instances if inst is not None]
    else:
        instances = list_instances()

    if not instances:
        return {
            "checked": 0,
            "updated": 0,
            "transitions": [],
            "started_at": _now(),
            "finished_at": _now(),
        }

    started_at = _now()
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    grouped = _group_by_region(instances)

    new_states: Dict[str, str] = {}
    for region, region_instances in grouped.items():
        try:
            region_result = await asyncio.to_thread(
                _reconcile_region_sync,
                boto3_module,
                region,
                region_instances,
                aws_access_key_id,
                aws_secret_access_key,
            )
        except Exception:
            for inst in region_instances:
                new_states[inst["id"]] = inst.get("state", "unknown")
            continue
        new_states.update(region_result)

    transitions = []
    updated = 0
    for inst in instances:
        instance_id = inst["id"]
        previous = inst.get("state", "unknown")
        latest = new_states.get(instance_id, previous)
        if latest != previous:
            updated += 1
            transitions.append(
                {
                    "instance_id": instance_id,
                    "from": previous,
                    "to": latest,
                }
            )
            if latest == "terminated":
                mark_instance_missing(instance_id)
            else:
                refreshed = dict(inst)
                refreshed["state"] = latest
                save_instance(refreshed)
        else:
            refreshed = dict(inst)
            refreshed["state"] = latest
            save_instance(refreshed)

    return {
        "checked": len(instances),
        "updated": updated,
        "transitions": transitions,
        "started_at": started_at,
        "finished_at": _now(),
    }
