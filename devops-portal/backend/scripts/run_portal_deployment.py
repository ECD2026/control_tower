"""
Entry point used by .github/workflows/portal-deploy.yml.

Rebuilds the DeploymentRequest from the environment variables the workflow
sets from its inputs, then runs the same Terraform + Ansible pipeline the
backend uses in local mode. AWS credentials and the SSH key are prepared
beforehand by scripts/open_workflow_bundle.py.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.schemas import DeploymentRequest  # noqa: E402
from services.local_executor import run_local_deployment  # noqa: E402


def _request_from_env() -> DeploymentRequest:
    payload = {
        "deployment_id": os.getenv("DEPLOYMENT_ID") or None,
        "name": os.getenv("DEPLOYMENT_NAME", ""),
        "provider": os.getenv("PROVIDER", "aws"),
        "region": os.getenv("REGION", "us-east-1"),
        "instance_type": os.getenv("INSTANCE_TYPE", "t2.micro"),
        "instances": int(os.getenv("INSTANCE_COUNT", "1")),
        "key_pair_name": os.getenv("KEY_PAIR_NAME", ""),
        "ssh_public_key": os.getenv("SSH_PUBLIC_KEY") or None,
        "security_group_ports": json.loads(
            os.getenv("SECURITY_GROUP_PORTS_JSON", "[22, 80, 443]")
        ),
        "os_type": os.getenv("OS_TYPE", "amazon_linux"),
        "packages": json.loads(os.getenv("PACKAGES_JSON", "[]")),
        "custom_commands": os.getenv("CUSTOM_COMMANDS", ""),
        "docker_image": os.getenv("DOCKER_IMAGE", ""),
        "detailed_monitoring": os.getenv("DETAILED_MONITORING", "true").lower() == "true",
    }
    return DeploymentRequest(**payload)


async def _log_to_stdout(message: str) -> None:
    print(message, flush=True)


async def main() -> int:
    mode = os.getenv("DEPLOY_MODE", "plan").strip().lower()
    request = _request_from_env()
    work_dir = tempfile.mkdtemp(prefix="portal_")
    # The portal records instances itself (by EC2 tag) once the run finishes,
    # so deployment_id is not passed here - the runner's DB is throwaway.
    await run_local_deployment(request, work_dir, mode, _log_to_stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
