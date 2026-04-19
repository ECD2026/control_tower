"""
Day-2 instance routes:
  GET  /api/instances                                       - list persisted instances
  GET  /api/instances/{instance_id}                         - detail + recent configurations
  POST /api/instances/{instance_id}/configure               - launch a package/command job
  GET  /api/instances/configurations/{config_id}/stream     - SSE live log stream
  GET  /api/instances/configurations/{config_id}/status     - quick status check
  POST /api/instances/reconcile                             - sync state with AWS
"""

import asyncio
import json
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database.db import (
    get_instance,
    get_instance_configuration,
    list_instance_configurations,
    list_instances,
    save_instance_configuration,
    update_instance_configuration_status,
)
from services.instance_configurator import configure_instance

router = APIRouter()


# In-memory state mirroring the deploy route's pattern.
active_queues: Dict[str, asyncio.Queue] = {}
configuration_statuses: Dict[str, str] = {}
configuration_logs_store: Dict[str, List[str]] = {}


class InstanceConfigurationRequest(BaseModel):
    packages: List[str] = Field(default_factory=list)
    custom_commands: str = ""


@router.get("/instances")
async def list_all_instances(state: Optional[str] = None):
    rows = list_instances(state=state)
    return [
        {
            "id": row["id"],
            "deployment_id": row["deployment_id"],
            "public_ip": row.get("public_ip"),
            "private_ip": row.get("private_ip"),
            "ssh_user": row.get("ssh_user"),
            "key_pair_name": row.get("key_pair_name"),
            "os_type": row.get("os_type"),
            "region": row.get("region"),
            "instance_type": row.get("instance_type"),
            "state": row.get("state", "unknown"),
            "tags": json.loads(row.get("tags") or "{}"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "last_seen_at": row.get("last_seen_at"),
        }
        for row in rows
    ]


@router.get("/instances/{instance_id}")
async def get_instance_detail(instance_id: str):
    inst = get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    configurations = list_instance_configurations(instance_id)
    for cfg in configurations:
        cfg["packages"] = json.loads(cfg.get("packages") or "[]")
        cfg["logs"] = json.loads(cfg.get("logs") or "[]")
    inst["tags"] = json.loads(inst.get("tags") or "{}")
    return {
        "instance": inst,
        "configurations": configurations,
    }


async def _run_configuration(
    configuration_id: str,
    instance: dict,
    packages: List[str],
    custom_commands: str,
) -> None:
    queue = active_queues[configuration_id]
    logs = configuration_logs_store[configuration_id]

    async def log(message: str) -> None:
        await queue.put(message)
        logs.append(message)

    try:
        configuration_statuses[configuration_id] = "running"
        update_instance_configuration_status(configuration_id, "running")
        await configure_instance(instance, packages, custom_commands, log)
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
):
    inst = get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
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
    inst["tags"] = json.loads(inst.get("tags") or "{}")

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
    )

    return {
        "configuration_id": configuration_id,
        "instance_id": instance_id,
        "status": "pending",
    }


@router.get("/instances/configurations/{configuration_id}/stream")
async def stream_configuration_logs(configuration_id: str):
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
                message = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield "data: [TIMEOUT] No activity for 120 s\n\n"
                yield "data: __DONE__\n\n"
                break

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
async def get_configuration_status(configuration_id: str):
    record = get_instance_configuration(configuration_id) or {}
    status = configuration_statuses.get(configuration_id, record.get("status", "unknown"))
    return {
        "configuration_id": configuration_id,
        "instance_id": record.get("instance_id"),
        "status": status,
    }


class ReconcileRequest(BaseModel):
    instance_ids: Optional[List[str]] = None


@router.post("/instances/reconcile")
async def reconcile(body: Optional[ReconcileRequest] = None):
    from services.aws_reconciler import reconcile_instances

    try:
        summary = await reconcile_instances(
            instance_ids=body.instance_ids if body else None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return summary
