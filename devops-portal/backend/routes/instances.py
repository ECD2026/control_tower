"""
Day-2 instance routes (all scoped to the logged-in user):
  GET    /api/instances                                    - list instances
  GET    /api/instances/{instance_id}                      - detail + recent configurations
  POST   /api/instances/{instance_id}/start                - resume a paused (stopped) instance
  POST   /api/instances/{instance_id}/stop                 - pause (stop) a running instance
  POST   /api/instances/{instance_id}/reboot               - restart a running instance
  DELETE /api/instances/{instance_id}                      - terminate the instance
  POST   /api/instances/{instance_id}/configure            - launch a package/command job
  GET    /api/instances/{instance_id}/monitoring           - Grafana/Prometheus links + live metrics
  GET    /api/instances/configurations/{config_id}/stream  - SSE live log stream
  GET    /api/instances/configurations/{config_id}/status  - quick status check
  POST   /api/instances/reconcile                          - sync state with AWS

EC2 calls use the AWS credential that created the instance. Start/stop/reboot
return immediately with a transitional state; a background task then polls
EC2 until the instance settles and records its new public IP.
"""

import asyncio
import json
import os
import uuid
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database.db import (
    get_credential,
    get_instance,
    get_instance_configuration,
    list_instance_configurations,
    list_instances,
    save_instance_configuration,
    update_instance_configuration_status,
    update_instance_state,
)
from services.auth import get_current_user
from services.aws_clients import session_for_credential
from services.aws_reconciler import reconcile_instances, wait_for_stable_state
from services.instance_configurator import configure_instance
from services.metrics_query import instance_snapshot
from services.prometheus_targets import rewrite_targets

router = APIRouter()


# In-memory state mirroring the deploy route's pattern.
active_queues: Dict[str, asyncio.Queue] = {}
configuration_statuses: Dict[str, str] = {}
configuration_logs_store: Dict[str, List[str]] = {}


class InstanceConfigurationRequest(BaseModel):
    packages: List[str] = Field(default_factory=list)
    custom_commands: str = ""


def _parse_tags(tags) -> dict:
    if isinstance(tags, dict):
        return tags
    try:
        parsed = json.loads(tags or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _node_exporter_enabled(tags) -> bool:
    return str(_parse_tags(tags).get("monitoring", "")).lower() == "enabled"


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row.get("name") or _parse_tags(row.get("tags")).get("Name"),
        "deployment_id": row["deployment_id"],
        "credential_id": row.get("credential_id"),
        "public_ip": row.get("public_ip"),
        "private_ip": row.get("private_ip"),
        "ssh_user": row.get("ssh_user"),
        "key_pair_name": row.get("key_pair_name"),
        "os_type": row.get("os_type"),
        "region": row.get("region"),
        "instance_type": row.get("instance_type"),
        "state": row.get("state", "unknown"),
        "tags": _parse_tags(row.get("tags")),
        "node_exporter": _node_exporter_enabled(row.get("tags")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_seen_at": row.get("last_seen_at"),
    }


def _owned_instance(instance_id: str, user: dict) -> dict:
    inst = get_instance(instance_id, user["id"])
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    return inst


def _credential_for(inst: dict) -> Optional[dict]:
    return get_credential(inst["credential_id"]) if inst.get("credential_id") else None


@router.get("/instances")
async def list_all_instances(
    state: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    return [_serialize(row) for row in list_instances(state=state, user_id=user["id"])]


@router.get("/instances/{instance_id}")
async def get_instance_detail(instance_id: str, user: dict = Depends(get_current_user)):
    inst = _owned_instance(instance_id, user)
    configurations = list_instance_configurations(instance_id)
    for cfg in configurations:
        cfg["packages"] = json.loads(cfg.get("packages") or "[]")
        cfg["logs"] = json.loads(cfg.get("logs") or "[]")
    return {
        "instance": _serialize(inst),
        "configurations": configurations,
    }


# ---------- Power actions ----------

# action -> (EC2 client method, states it is allowed from, transitional state)
_POWER_ACTIONS = {
    "start": ("start_instances", {"stopped"}, "pending"),
    "stop": ("stop_instances", {"running", "pending"}, "stopping"),
    "reboot": ("reboot_instances", {"running"}, "pending"),
}


async def _power_action(
    action: str,
    instance_id: str,
    user: dict,
    background_tasks: BackgroundTasks,
) -> dict:
    inst = _owned_instance(instance_id, user)
    method, allowed_from, transitional = _POWER_ACTIONS[action]
    if inst.get("state") not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot {action} an instance that is '{inst.get('state')}'.",
        )

    try:
        client = session_for_credential(_credential_for(inst), inst.get("region")).client("ec2")
        await asyncio.to_thread(getattr(client, method), InstanceIds=[instance_id])
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AWS rejected the {action} request: {exc}",
        ) from exc

    update_instance_state(instance_id, transitional)
    rewrite_targets()
    background_tasks.add_task(wait_for_stable_state, instance_id)
    return {"instance_id": instance_id, "action": action, "state": transitional}


@router.post("/instances/{instance_id}/start")
async def start_instance(
    instance_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    return await _power_action("start", instance_id, user, background_tasks)


@router.post("/instances/{instance_id}/stop")
async def stop_instance(
    instance_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    return await _power_action("stop", instance_id, user, background_tasks)


@router.post("/instances/{instance_id}/reboot")
async def reboot_instance(
    instance_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    return await _power_action("reboot", instance_id, user, background_tasks)


@router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str, user: dict = Depends(get_current_user)):
    inst = _owned_instance(instance_id, user)

    if inst.get("state") != "terminated":
        try:
            client = session_for_credential(_credential_for(inst), inst.get("region")).client(
                "ec2"
            )
            await asyncio.to_thread(client.terminate_instances, InstanceIds=[instance_id])
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to terminate instance in AWS: {exc}",
            ) from exc

    update_instance_state(instance_id, "terminated")
    rewrite_targets()
    return {
        "instance_id": instance_id,
        "action": "delete",
        "state": "terminated",
    }


# ---------- Day-2 configuration ----------


async def _run_configuration(
    configuration_id: str,
    instance: dict,
    packages: List[str],
    custom_commands: str,
    credential: Optional[dict],
) -> None:
    queue = active_queues[configuration_id]
    logs = configuration_logs_store[configuration_id]

    async def log(message: str) -> None:
        await queue.put(message)
        logs.append(message)

    try:
        configuration_statuses[configuration_id] = "running"
        update_instance_configuration_status(configuration_id, "running")
        await configure_instance(instance, packages, custom_commands, log, credential)
        configuration_statuses[configuration_id] = "success"
    except Exception as exc:
        configuration_statuses[configuration_id] = "failed"
        await log(f"[ERROR] {type(exc).__name__}: {exc}")
    finally:
        update_instance_configuration_status(
            configuration_id,
            configuration_statuses[configuration_id],
            logs,
        )
        await queue.put("__DONE__")
        active_queues.pop(configuration_id, None)
        configuration_statuses.pop(configuration_id, None)
        configuration_logs_store.pop(configuration_id, None)


@router.post("/instances/{instance_id}/configure")
async def configure(
    instance_id: str,
    body: InstanceConfigurationRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    inst = _owned_instance(instance_id, user)
    if inst.get("state") not in (None, "running"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Instance state is '{inst.get('state')}'. "
                f"Only 'running' instances can be reconfigured."
            ),
        )
    if not body.packages and not body.custom_commands.strip():
        raise HTTPException(
            status_code=400,
            detail="Provide at least one package or a non-empty custom_commands value.",
        )

    configuration_id = str(uuid.uuid4())
    active_queues[configuration_id] = asyncio.Queue()
    configuration_statuses[configuration_id] = "pending"
    configuration_logs_store[configuration_id] = []
    inst["tags"] = _parse_tags(inst.get("tags"))

    save_instance_configuration(
        configuration_id,
        instance_id,
        body.packages,
        body.custom_commands,
    )

    background_tasks.add_task(
        _run_configuration,
        configuration_id,
        inst,
        body.packages,
        body.custom_commands,
        _credential_for(inst),
    )

    return {
        "configuration_id": configuration_id,
        "instance_id": instance_id,
        "status": "pending",
    }


def _owned_configuration(configuration_id: str, user: dict) -> dict:
    record = get_instance_configuration(configuration_id)
    if not record or not get_instance(record["instance_id"], user["id"]):
        raise HTTPException(status_code=404, detail="Configuration not found")
    return record


@router.get("/instances/configurations/{configuration_id}/stream")
async def stream_configuration_logs(
    configuration_id: str,
    user: dict = Depends(get_current_user),
):
    _owned_configuration(configuration_id, user)

    async def event_gen():
        queue = active_queues.get(configuration_id)
        if not queue:
            record = get_instance_configuration(configuration_id)
            if record:
                for line in json.loads(record.get("logs", "[]")):
                    yield f"data: {line}\n\n"
            yield "data: __DONE__\n\n"
            return

        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                if configuration_id not in active_queues:
                    yield "data: __DONE__\n\n"
                    break
                yield ": keepalive\n\n"
                continue

            if message == "__DONE__":
                yield "data: __DONE__\n\n"
                break

            yield f"data: {message}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/instances/configurations/{configuration_id}/status")
async def get_configuration_status(
    configuration_id: str,
    user: dict = Depends(get_current_user),
):
    record = _owned_configuration(configuration_id, user)
    status = configuration_statuses.get(configuration_id, record.get("status", "unknown"))
    return {
        "configuration_id": configuration_id,
        "instance_id": record.get("instance_id"),
        "status": status,
    }


# ---------- Reconcile + monitoring ----------


class ReconcileRequest(BaseModel):
    instance_ids: Optional[List[str]] = None


@router.post("/instances/reconcile")
async def reconcile(
    body: Optional[ReconcileRequest] = None,
    user: dict = Depends(get_current_user),
):
    try:
        return await reconcile_instances(
            instance_ids=body.instance_ids if body else None,
            user_id=user["id"],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def grafana_base_url() -> str:
    # Relative by default: nginx serves Grafana on the same origin at /grafana.
    return os.getenv("GRAFANA_PUBLIC_URL", "/grafana").rstrip("/")


@router.get("/instances/{instance_id}/monitoring")
async def get_instance_monitoring(instance_id: str, user: dict = Depends(get_current_user)):
    inst = _owned_instance(instance_id, user)
    dashboard_uid = os.getenv("GRAFANA_DASHBOARD_UID", "instance-overview")
    instance_q = quote_plus(instance_id)
    snapshot = await asyncio.to_thread(instance_snapshot, instance_id)

    return {
        # CloudWatch covers every instance that exists; node_exporter adds
        # memory/disk detail when it has been installed.
        "enabled": inst.get("state") != "terminated",
        "node_exporter": _node_exporter_enabled(inst.get("tags")),
        "grafana_url": (
            f"{grafana_base_url()}/d/{dashboard_uid}/instance-overview"
            f"?var-instance={instance_q}&orgId=1&refresh=1m"
        ),
        "prometheus_url": (
            "/prometheus/graph"
            f"?g0.expr=aws_ec2_cpuutilization_average%7Binstance_id%3D%22{instance_q}%22%7D"
        ),
        **snapshot,
    }
