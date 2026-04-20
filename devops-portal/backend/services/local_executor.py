import json
import os
import sys
from datetime import datetime, timezone
from typing import List

from database.db import save_instances
from executor.runner import execute_command
from generators.ansible_gen import generate_ansible
from generators.terraform_gen import generate_terraform
from models.schemas import DeploymentRequest
from services.prometheus_targets import rewrite_targets

from services.execution_types import ExecutionResult, LogFn

SSH_CONNECT_TIMEOUT_SECONDS = 5
SSH_WAIT_INTERVAL_SECONDS = 5
SSH_WAIT_TIMEOUT_SECONDS = 300

SSH_KEY_DIR_ENV = os.getenv("SSH_KEY_DIR")
DEFAULT_SSH_KEY_DIR = (
    os.path.expanduser(SSH_KEY_DIR_ENV)
    if SSH_KEY_DIR_ENV
    else (
        "/home/asus/.ssh"
        if sys.platform == "win32"
        else os.path.expanduser("~/.ssh")
    )
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


async def _wait_for_ssh(
    ip: str,
    ssh_user: str,
    ssh_key_path: str,
    work_dir: str,
    log: LogFn,
) -> None:
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + SSH_WAIT_TIMEOUT_SECONDS
    attempt = 1
    target = f"{ssh_user}@{ip}"

    while True:
        await log(f"[{_ts()}] Waiting for SSH on {ip} (attempt {attempt})")
        try:
            if sys.platform == "win32":
                ssh_cmd = [
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
                ]
            else:
                ssh_cmd = [
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
                ]

            async for line in execute_command(
                ssh_cmd,
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


async def run_local_deployment(
    request: DeploymentRequest,
    work_dir: str,
    mode: str,
    log: LogFn,
    deployment_id: str | None = None,
) -> ExecutionResult:
    await log(f"[{_ts()}] Starting {'plan' if mode == 'plan' else 'deployment'}")
    await log(f"[{_ts()}] Work directory: {work_dir}")

    await log(f"[{_ts()}] Generating Terraform configuration")
    tf_path = os.path.join(work_dir, "main.tf")
    with open(tf_path, "w", encoding="utf-8") as fh:
        fh.write(generate_terraform(request))
    await log(f"[{_ts()}] main.tf written")

    await log(f"[{_ts()}] Generating Ansible playbook")
    ansible_path = os.path.join(work_dir, "setup.yml")
    with open(ansible_path, "w", encoding="utf-8") as fh:
        fh.write(generate_ansible(request))
    await log(f"[{_ts()}] setup.yml written")

    await log(f"[{_ts()}] Running: terraform init")
    async for line in execute_command(["terraform", "init", "-no-color"], work_dir):
        await log(f"[TERRAFORM] {line}")

    if mode == "plan":
        await log(f"[{_ts()}] Running: terraform plan")
        async for line in execute_command(["terraform", "plan", "-no-color"], work_dir):
            await log(f"[TERRAFORM] {line}")

        await log(f"[{_ts()}] Terraform plan completed successfully")
        return ExecutionResult(status="success", execution_mode="local")

    await log(f"[{_ts()}] Running: terraform apply")
    async for line in execute_command(
        ["terraform", "apply", "-auto-approve", "-no-color"], work_dir
    ):
        await log(f"[TERRAFORM] {line}")

    await log(f"[{_ts()}] Fetching terraform outputs")
    output_lines: List[str] = []
    async for line in execute_command(["terraform", "output", "-json"], work_dir):
        output_lines.append(line)

    ips: List[str] = []
    instance_ids: List[str] = []
    private_ips: List[str] = []
    try:
        tf_outputs = json.loads("\n".join(output_lines))
        ips = tf_outputs.get("instance_public_ips", {}).get("value", [])
        instance_ids = tf_outputs.get("instance_ids", {}).get("value", [])
        private_ips = tf_outputs.get("instance_private_ips", {}).get("value", [])
    except Exception as exc:
        await log(f"[WARNING] Could not parse Terraform outputs: {exc}")

    if not ips:
        await log(
            "[WARNING] No public IPs found in Terraform output; "
            "skipping Ansible provisioning."
        )
        await log(f"[{_ts()}] Deployment completed successfully")
        return ExecutionResult(status="success", execution_mode="local")

    await log(f"[{_ts()}] EC2 instances created:")
    for index, ip in enumerate(ips, start=1):
        await log(f"[INFO]   Server {index}: {ip}")

    ssh_user = "ubuntu" if request.os_type == "ubuntu" else "ec2-user"
    ssh_key_path = f"{DEFAULT_SSH_KEY_DIR}/{request.key_pair_name}.pem"

    if deployment_id and instance_ids:
        monitoring_enabled = "node_exporter" in [pkg.lower() for pkg in request.packages]
        persisted: List[dict] = []
        for index, tf_id in enumerate(instance_ids):
            tags = {
                "Name": f"devops-portal-server-{index + 1}",
                "Environment": "devops-portal",
                "ManagedBy": "DevOpsAutomationPortal",
            }
            if monitoring_enabled:
                tags["monitoring"] = "enabled"
            persisted.append(
                {
                    "id": tf_id,
                    "public_ip": ips[index] if index < len(ips) else None,
                    "private_ip": (
                        private_ips[index] if index < len(private_ips) else None
                    ),
                    "ssh_user": ssh_user,
                    "key_pair_name": request.key_pair_name,
                    "os_type": request.os_type,
                    "region": request.region,
                    "instance_type": request.instance_type,
                    "state": "running",
                    "tags": tags,
                }
            )
        try:
            save_instances(deployment_id, persisted)
            rewrite_targets()
            await log(
                f"[{_ts()}] Persisted {len(persisted)} instance record(s) "
                f"to local inventory"
            )
        except Exception as exc:
            await log(f"[WARNING] Could not persist instance records: {exc}")
    inventory_path = os.path.join(work_dir, "inventory.ini")
    inventory_lines = ["[servers]"]
    for index, ip in enumerate(ips, start=1):
        inventory_lines.append(
            f"server{index} ansible_host={ip} "
            f"ansible_user={ssh_user} "
            f"ansible_ssh_private_key_file={ssh_key_path}"
        )
    with open(inventory_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(inventory_lines) + "\n")
    await log(f"[{_ts()}] Ansible inventory written")

    await log(f"[{_ts()}] Waiting for SSH to become available")
    for ip in ips:
        await _wait_for_ssh(ip, ssh_user, ssh_key_path, work_dir, log)

    await log(f"[{_ts()}] Running: ansible-playbook")
    async for line in execute_command(
        [
            "ansible-playbook",
            "-i",
            inventory_path,
            ansible_path,
            "--ssh-extra-args=-o StrictHostKeyChecking=no",
        ],
        work_dir,
    ):
        await log(f"[ANSIBLE] {line}")

    await log(f"[{_ts()}] Ansible playbook completed successfully")
    await log(f"[{_ts()}] Deployment completed successfully")
    return ExecutionResult(status="success", execution_mode="local")
