"""
Deployment routes (all require a logged-in user):
  POST /api/plan   - run a planning workflow
  POST /api/deploy - run a deployment workflow
  GET  /api/deploy/{id}/stream - SSE log stream (cookie-authenticated)
  GET  /api/deploy/{id}/status - quick status check

The request names one of the user's stored credentials; the key pair and AWS
keys used for the run come from that credential, never from the form.
"""

import asyncio
import json
import tempfile
import uuid
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database.db import (
    get_credential,
    get_deployment,
    save_deployment,
    update_deployment_execution_metadata,
    update_deployment_status,
)
from models.schemas import DeploymentRequest, DeploymentResponse
from services.auth import get_current_user
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
    credential: dict | None,
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
            credential=credential,
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


def _create_job(
    request: DeploymentRequest, user: dict, mode: str
) -> tuple[str, str, DeploymentRequest, dict]:
    if not request.credential_id:
        raise HTTPException(
            status_code=400,
            detail="Select AWS credentials (add them on the Credentials page first).",
        )
    credential = get_credential(request.credential_id, user["id"])
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    if not credential.get("ssh_public_key"):
        raise HTTPException(
            status_code=400,
            detail="This credential has no SSH key pair yet - add one on the Credentials page.",
        )

    deployment_id = str(uuid.uuid4())
    # Fields derived server-side so the form cannot point at someone else's key.
    request = request.model_copy(
        update={
            "deployment_id": deployment_id,
            "key_pair_name": credential["key_pair_name"],
            "ssh_public_key": credential["ssh_public_key"],
        }
    )
    work_dir = tempfile.mkdtemp(prefix=f"devops_{deployment_id[:8]}_")
    active_queues[deployment_id] = asyncio.Queue()
    deployment_statuses[deployment_id] = "pending"
    deployment_logs_store[deployment_id] = []
    save_deployment(
        deployment_id,
        {**request.model_dump(), "mode": mode},
        execution_mode=get_execution_mode(),
        user_id=user["id"],
        credential_id=credential["id"],
    )
    return deployment_id, work_dir, request, credential


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


def _start(mode: str, request: DeploymentRequest, user: dict, tasks: BackgroundTasks):
    deployment_id, work_dir, request, credential = _create_job(request, user, mode)
    tasks.add_task(run_deployment, deployment_id, request, work_dir, mode, credential)
    return _response_from_record(deployment_id, "pending", work_dir)


@router.post("/plan", response_model=DeploymentResponse)
async def plan_infrastructure(
    request: DeploymentRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    return _start("plan", request, user, background_tasks)


@router.post("/deploy", response_model=DeploymentResponse)
async def deploy_infrastructure(
    request: DeploymentRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    return _start("deploy", request, user, background_tasks)


def _owned_deployment(deployment_id: str, user: dict) -> dict:
    record = get_deployment(deployment_id, user["id"])
    if not record:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return record


@router.get("/deploy/{deployment_id}/stream")
async def stream_logs(deployment_id: str, user: dict = Depends(get_current_user)):
    _owned_deployment(deployment_id, user)

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
                message = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                if deployment_id not in active_queues:
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


@router.get("/deploy/{deployment_id}/status")
async def get_status(deployment_id: str, user: dict = Depends(get_current_user)):
    record = _owned_deployment(deployment_id, user)
    status = deployment_statuses.get(deployment_id, record.get("status", "unknown"))
    return {
        "deployment_id": deployment_id,
        "status": status,
        "execution_mode": record.get("execution_mode"),
        "external_ref": record.get("external_ref"),
        "external_url": record.get("external_url"),
    }
