"""
Deployment routes:
  POST /api/plan   – generate Terraform + Ansible files, run `terraform plan`
  POST /api/deploy – run the full Terraform apply + Ansible playbook
  GET  /api/deploy/{id}/stream  – SSE log stream
  GET  /api/deploy/{id}/status  – quick status check
"""

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from database.db import save_deployment, update_deployment_status
from executor.runner import execute_command
from generators.ansible_gen import generate_ansible
from generators.terraform_gen import generate_terraform
from models.schemas import DeploymentRequest, DeploymentResponse

router = APIRouter()

SSH_CONNECT_TIMEOUT_SECONDS = 5
SSH_WAIT_INTERVAL_SECONDS = 5
SSH_WAIT_TIMEOUT_SECONDS = 300
WSL_SSH_KEY_DIR = "/home/asus/.ssh"

# ---------- In-memory state for active deployments ----------
active_queues: Dict[str, asyncio.Queue] = {}
deployment_statuses: Dict[str, str] = {}
deployment_logs_store: Dict[str, List[str]] = {}
LogFn = Callable[[str], Awaitable[None]]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


async def _wait_for_ssh(
    ip: str,
    ssh_user: str,
    ssh_key_path: str,
    work_dir: str,
    log: LogFn,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SSH_WAIT_TIMEOUT_SECONDS
    attempt = 1
    target = f"{ssh_user}@{ip}"

    while True:
        await log(f"[{_ts()}] Waiting for SSH on {ip} (attempt {attempt})")
        try:
            async for line in execute_command(
                [
                    "wsl",
                    "--",
                    "ssh",
                    "-i",
                    ssh_key_path,
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-o",
                    "ConnectionAttempts=1",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    target,
                    "true",
                ],
                work_dir,
            ):
                if line:
                    await log(f"[SSH] {line}")

            await log(f"[{_ts()}] SSH ready on {ip}")
            return
        except RuntimeError as exc:
            error_text = str(exc)
            if "Identity file" in error_text and "not accessible" in error_text:
                raise RuntimeError(
                    f"SSH key is not accessible in WSL: {ssh_key_path}"
                ) from exc

            if loop.time() >= deadline:
                raise TimeoutError(
                    f"SSH did not become ready on {ip} within "
                    f"{SSH_WAIT_TIMEOUT_SECONDS} seconds."
                ) from exc

            await log(
                f"[SSH] {ip} is not ready yet; retrying in "
                f"{SSH_WAIT_INTERVAL_SECONDS} seconds..."
            )
            await asyncio.sleep(SSH_WAIT_INTERVAL_SECONDS)
            attempt += 1


# ---------- Core execution logic ----------

async def run_deployment(
    deployment_id: str,
    request: DeploymentRequest,
    work_dir: str,
    mode: str,  # "plan" | "deploy"
) -> None:
    queue = active_queues[deployment_id]
    logs = deployment_logs_store[deployment_id]

    async def log(msg: str) -> None:
        await queue.put(msg)
        logs.append(msg)

    try:
        deployment_statuses[deployment_id] = "running"
        await log(f"[{_ts()}] Starting {'plan' if mode == 'plan' else 'deployment'}…")
        await log(f"[{_ts()}] Work directory: {work_dir}")

        # ── Generate Terraform ──────────────────────────────────────────────
        await log(f"[{_ts()}] Generating Terraform configuration…")
        tf_path = os.path.join(work_dir, "main.tf")
        with open(tf_path, "w") as fh:
            fh.write(generate_terraform(request))
        await log(f"[{_ts()}] ✔  main.tf written")

        # ── Generate Ansible ────────────────────────────────────────────────
        await log(f"[{_ts()}] Generating Ansible playbook…")
        ansible_path = os.path.join(work_dir, "setup.yml")
        with open(ansible_path, "w") as fh:
            fh.write(generate_ansible(request))
        await log(f"[{_ts()}] ✔  setup.yml written")

        # ── terraform init ──────────────────────────────────────────────────
        await log(f"[{_ts()}] Running: terraform init")
        async for line in execute_command(
            ["terraform", "init", "-no-color"], work_dir
        ):
            await log(f"[TERRAFORM] {line}")

        if mode == "plan":
            # ── terraform plan only ─────────────────────────────────────────
            await log(f"[{_ts()}] Running: terraform plan")
            async for line in execute_command(
                ["terraform", "plan", "-no-color"], work_dir
            ):
                await log(f"[TERRAFORM] {line}")

            deployment_statuses[deployment_id] = "success"
            await log(f"[{_ts()}] ✔  Terraform plan completed successfully!")

        else:
            # ── terraform apply ─────────────────────────────────────────────
            await log(f"[{_ts()}] Running: terraform apply")
            async for line in execute_command(
                ["terraform", "apply", "-auto-approve", "-no-color"], work_dir
            ):
                await log(f"[TERRAFORM] {line}")

            # ── Fetch outputs (public IPs) ───────────────────────────────────
            await log(f"[{_ts()}] Fetching terraform outputs…")
            output_lines: List[str] = []
            async for line in execute_command(
                ["terraform", "output", "-json"], work_dir
            ):
                output_lines.append(line)

            try:
                tf_outputs = json.loads("\n".join(output_lines))
                ips: List[str] = (
                    tf_outputs.get("instance_public_ips", {}).get("value", [])
                )
            except Exception as exc:
                await log(f"[WARNING] Could not parse Terraform outputs: {exc}")
                ips = []

            if ips:
                await log(f"[{_ts()}] ✔  EC2 instances created:")
                for i, ip in enumerate(ips):
                    await log(f"[INFO]   Server {i + 1}: {ip}")

                # ── Build Ansible inventory ──────────────────────────────────
                ssh_user = "ubuntu" if request.os_type == "ubuntu" else "ec2-user"
                ssh_key_path = f"{WSL_SSH_KEY_DIR}/{request.key_pair_name}.pem"
                inv_lines = ["[servers]"]
                for i, ip in enumerate(ips):
                    inv_lines.append(
                        f"server{i + 1} ansible_host={ip} "
                        f"ansible_user={ssh_user} "
                        # WSL home directory — key must exist at ~/.ssh/ inside WSL
                        f"ansible_ssh_private_key_file={ssh_key_path}"
                    )
                inventory_path = os.path.join(work_dir, "inventory.ini")
                with open(inventory_path, "w") as fh:
                    fh.write("\n".join(inv_lines) + "\n")
                await log(f"[{_ts()}] ✔  Ansible inventory written")

                # ── Wait for SSH ─────────────────────────────────────────────
                await log(f"[{_ts()}] Waiting for SSH to become available...")
                for ip in ips:
                    await _wait_for_ssh(ip, ssh_user, ssh_key_path, work_dir, log)

                # ── Run Ansible ──────────────────────────────────────────────
                await log(f"[{_ts()}] Running: ansible-playbook")
                async for line in execute_command(
                    [
                        "ansible-playbook",
                        "-i", inventory_path,
                        ansible_path,
                        "--ssh-extra-args=-o StrictHostKeyChecking=no",
                    ],
                    work_dir,
                ):
                    await log(f"[ANSIBLE] {line}")

                await log(f"[{_ts()}] ✔  Ansible playbook completed!")
            else:
                await log(
                    f"[WARNING] No public IPs found in Terraform output — "
                    "skipping Ansible provisioning."
                )

            deployment_statuses[deployment_id] = "success"
            await log(f"[{_ts()}] ✔  Deployment completed successfully!")

    except Exception as exc:
        deployment_statuses[deployment_id] = "failed"
        await log(f"[ERROR] {type(exc).__name__}: {exc}")

    finally:
        update_deployment_status(
            deployment_id, deployment_statuses[deployment_id], logs
        )
        await queue.put("__DONE__")


# ---------- Routes ----------

def _create_job(request: DeploymentRequest) -> tuple[str, str]:
    deployment_id = str(uuid.uuid4())
    work_dir = tempfile.mkdtemp(prefix=f"devops_{deployment_id[:8]}_")
    active_queues[deployment_id] = asyncio.Queue()
    deployment_statuses[deployment_id] = "pending"
    deployment_logs_store[deployment_id] = []
    save_deployment(deployment_id, request.model_dump())
    return deployment_id, work_dir


@router.post("/plan", response_model=DeploymentResponse)
async def plan_infrastructure(
    request: DeploymentRequest, background_tasks: BackgroundTasks
):
    deployment_id, work_dir = _create_job(request)
    background_tasks.add_task(run_deployment, deployment_id, request, work_dir, "plan")
    return DeploymentResponse(
        deployment_id=deployment_id, status="pending", work_dir=work_dir
    )


@router.post("/deploy", response_model=DeploymentResponse)
async def deploy_infrastructure(
    request: DeploymentRequest, background_tasks: BackgroundTasks
):
    deployment_id, work_dir = _create_job(request)
    background_tasks.add_task(
        run_deployment, deployment_id, request, work_dir, "deploy"
    )
    return DeploymentResponse(
        deployment_id=deployment_id, status="pending", work_dir=work_dir
    )


@router.get("/deploy/{deployment_id}/stream")
async def stream_logs(deployment_id: str):
    async def event_gen():
        queue = active_queues.get(deployment_id)
        if not queue:
            # Deployment already finished — send stored logs then close
            from database.db import get_deployment
            rec = get_deployment(deployment_id)
            if rec:
                for line in json.loads(rec.get("logs", "[]")):
                    yield f"data: {line}\n\n"
            yield "data: __DONE__\n\n"
            return

        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield "data: [TIMEOUT] No activity for 120 s\n\n"
                yield "data: __DONE__\n\n"
                break
            if msg == "__DONE__":
                yield "data: __DONE__\n\n"
                break
            yield f"data: {msg}\n\n"

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
    status = deployment_statuses.get(deployment_id)
    if status is None:
        from database.db import get_deployment
        rec = get_deployment(deployment_id)
        status = rec["status"] if rec else "unknown"
    return {"deployment_id": deployment_id, "status": status}
