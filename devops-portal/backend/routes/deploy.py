"""
Deployment routes:
  POST /api/plan   - run a planning workflow
  POST /api/deploy - run a deployment workflow
  GET  /api/deploy/{id}/stream - SSE log stream
  GET  /api/deploy/{id}/status - quick status check
"""

import asyncio
import json
import tempfile
import uuid
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from database.db import (
    get_deployment,
    save_deployment,
    update_deployment_execution_metadata,
    update_deployment_status,
)
from models.schemas import DeploymentRequest, DeploymentResponse
from services.deployment_execution import get_execution_mode, run_requested_deployment

router = APIRouter()

# In-memory state for active deployments.
active_queues: Dict[str, asyncio.Queue] = {}
deployment_statuses: Dict[str, str] = {}
deployment_logs_store: Dict[str, List[str]] = {}


async def run_deployment(
    deployment_id: str,
    request: DeploymentRequest,
    work_dir: str,
    mode: str,  # "plan" | "deploy"
) -> None:
    queue = active_queues[deployment_id]
    logs = deployment_logs_store[deployment_id]
    configured_mode = get_execution_mode()

    async def log(message: str) -> None:
        await queue.put(message)
        logs.append(message)

    async def remember_metadata(
        external_ref: str | None,
        external_url: str | None,
    ) -> None:
        update_deployment_execution_metadata(
            deployment_id,
            execution_mode=configured_mode,
            external_ref=external_ref,
            external_url=external_url,
        )

    try:
        deployment_statuses[deployment_id] = "running"
        update_deployment_status(deployment_id, "running")
        update_deployment_execution_metadata(
            deployment_id,
            execution_mode=configured_mode,
        )

        result = await run_requested_deployment(
            deployment_id=deployment_id,
            request=request,
            work_dir=work_dir,
            mode=mode,
            log=log,
            update_metadata=remember_metadata,
        )
        deployment_statuses[deployment_id] = result.status
        update_deployment_execution_metadata(
            deployment_id,
            execution_mode=result.execution_mode,
            external_ref=result.external_ref,
            external_url=result.external_url,
        )
    except Exception as exc:
        deployment_statuses[deployment_id] = "failed"
        await log(f"[ERROR] {type(exc).__name__}: {exc}")
    finally:
        update_deployment_status(
            deployment_id,
            deployment_statuses[deployment_id],
            logs,
        )
        await queue.put("__DONE__")
        active_queues.pop(deployment_id, None)
        deployment_statuses.pop(deployment_id, None)
        deployment_logs_store.pop(deployment_id, None)


def _create_job(request: DeploymentRequest) -> tuple[str, str, str]:
    deployment_id = str(uuid.uuid4())
    work_dir = tempfile.mkdtemp(prefix=f"devops_{deployment_id[:8]}_")
    execution_mode = get_execution_mode()
    active_queues[deployment_id] = asyncio.Queue()
    deployment_statuses[deployment_id] = "pending"
    deployment_logs_store[deployment_id] = []
    save_deployment(
        deployment_id,
        request.model_dump(),
        execution_mode=execution_mode,
    )
    return deployment_id, work_dir, execution_mode


def _response_from_record(
    deployment_id: str,
    status: str,
    work_dir: str,
) -> DeploymentResponse:
    record = get_deployment(deployment_id) or {}
    return DeploymentResponse(
        deployment_id=deployment_id,
        status=status,
        work_dir=work_dir,
        execution_mode=record.get("execution_mode", get_execution_mode()),
        external_ref=record.get("external_ref"),
        external_url=record.get("external_url"),
    )


@router.post("/plan", response_model=DeploymentResponse)
async def plan_infrastructure(
    request: DeploymentRequest, background_tasks: BackgroundTasks
):
    deployment_id, work_dir, _ = _create_job(request)
    background_tasks.add_task(run_deployment, deployment_id, request, work_dir, "plan")
    return _response_from_record(deployment_id, "pending", work_dir)


@router.post("/deploy", response_model=DeploymentResponse)
async def deploy_infrastructure(
    request: DeploymentRequest, background_tasks: BackgroundTasks
):
    deployment_id, work_dir, _ = _create_job(request)
    background_tasks.add_task(
        run_deployment, deployment_id, request, work_dir, "deploy"
    )
    return _response_from_record(deployment_id, "pending", work_dir)


@router.get("/deploy/{deployment_id}/stream")
async def stream_logs(deployment_id: str):
    async def event_gen():
        queue = active_queues.get(deployment_id)
        if not queue:
            record = get_deployment(deployment_id)
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


@router.get("/deploy/{deployment_id}/status")
async def get_status(deployment_id: str):
    record = get_deployment(deployment_id) or {}
    status = deployment_statuses.get(deployment_id, record.get("status", "unknown"))
    return {
        "deployment_id": deployment_id,
        "status": status,
        "execution_mode": record.get("execution_mode"),
        "external_ref": record.get("external_ref"),
        "external_url": record.get("external_url"),
    }
