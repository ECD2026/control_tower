"""
Day-2 instance configurator.

Runs Ansible against a single, already-provisioned EC2 instance so that users
can add extra packages or custom commands through the portal GUI without
standing up new infrastructure.
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import List

from executor.runner import execute_command
from generators.ansible_gen import generate_ansible_for_host

from services.execution_types import LogFn


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
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SSH_WAIT_TIMEOUT_SECONDS
    attempt = 1
    target = f"{ssh_user}@{ip}"

    while True:
        await log(f"[{_ts()}] Waiting for SSH on {ip} (attempt {attempt})")
        try:
            if sys.platform == "win32":
                ssh_cmd = [
                    "wsl", "--", "ssh",
                    "-i", ssh_key_path,
                    "-o", "BatchMode=yes",
                    "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-o", "ConnectionAttempts=1",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    target, "true",
                ]
            else:
                ssh_cmd = [
                    "ssh",
                    "-i", ssh_key_path,
                    "-o", "BatchMode=yes",
                    "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-o", "ConnectionAttempts=1",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    target, "true",
                ]

            async for line in execute_command(ssh_cmd, work_dir):
                if line:
                    await log(f"[SSH] {line}")

            await log(f"[{_ts()}] SSH ready on {ip}")
            return
        except RuntimeError as exc:
            error_text = str(exc)
            if "Identity file" in error_text and "not accessible" in error_text:
                raise RuntimeError(
                    f"SSH key is not accessible: {ssh_key_path}"
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


async def configure_instance(
    instance: dict,
    packages: List[str],
    custom_commands: str,
    log: LogFn,
) -> None:
    """
    Generate a single-host playbook for `instance`, wait for SSH, then run
    Ansible. All progress is streamed through `log`. Raises on any failure.
    """
    instance_id = instance.get("id")
    public_ip = instance.get("public_ip")
    ssh_user = instance.get("ssh_user") or (
        "ubuntu" if instance.get("os_type") == "ubuntu" else "ec2-user"
    )
    key_pair_name = instance.get("key_pair_name")

    if not public_ip:
        raise RuntimeError(
            f"Instance {instance_id} has no public IP — cannot configure over SSH."
        )
    if not key_pair_name:
        raise RuntimeError(
            f"Instance {instance_id} has no key_pair_name recorded — cannot "
            f"locate SSH key."
        )

    ssh_key_path = f"{DEFAULT_SSH_KEY_DIR}/{key_pair_name}.pem"

    work_dir = tempfile.mkdtemp(prefix=f"instance_cfg_{instance_id[:8]}_")
    await log(f"[{_ts()}] Work directory: {work_dir}")

    playbook_path = os.path.join(work_dir, "setup.yml")
    with open(playbook_path, "w", encoding="utf-8") as fh:
        fh.write(generate_ansible_for_host(instance, packages, custom_commands))
    await log(f"[{_ts()}] setup.yml written for instance {instance_id}")

    inventory_path = os.path.join(work_dir, "inventory.ini")
    inventory = (
        "[target]\n"
        f"host1 ansible_host={public_ip} "
        f"ansible_user={ssh_user} "
        f"ansible_ssh_private_key_file={ssh_key_path}\n"
    )
    with open(inventory_path, "w", encoding="utf-8") as fh:
        fh.write(inventory)
    await log(f"[{_ts()}] Inventory written ({public_ip})")

    await log(f"[{_ts()}] Waiting for SSH to become available")
    await _wait_for_ssh(public_ip, ssh_user, ssh_key_path, work_dir, log)

    await log(f"[{_ts()}] Running: ansible-playbook")
    async for line in execute_command(
        [
            "ansible-playbook",
            "-i", inventory_path,
            playbook_path,
            "--ssh-extra-args=-o StrictHostKeyChecking=no",
        ],
        work_dir,
    ):
        await log(f"[ANSIBLE] {line}")

    await log(f"[{_ts()}] Configuration completed successfully on {instance_id}")
