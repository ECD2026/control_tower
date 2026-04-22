import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.schemas import DeploymentRequest
from services.local_executor import run_local_deployment


def _request_from_env() -> DeploymentRequest:
    payload = {
        "provider": os.getenv("PROVIDER", "aws"),
        "region": os.getenv("REGION", "us-east-1"),
        "instance_type": os.getenv("INSTANCE_TYPE", "t2.micro"),
        "instances": int(os.getenv("INSTANCE_COUNT", "1")),
        "key_pair_name": os.getenv("KEY_PAIR_NAME", ""),
        "security_group_ports": json.loads(
            os.getenv("SECURITY_GROUP_PORTS_JSON", "[22, 80, 443]")
        ),
        "os_type": os.getenv("OS_TYPE", "amazon_linux"),
        "packages": json.loads(os.getenv("PACKAGES_JSON", "[]")),
        "custom_commands": os.getenv("CUSTOM_COMMANDS", ""),
        "docker_image": os.getenv("DOCKER_IMAGE", ""),
        "kubernetes": os.getenv("KUBERNETES", "false").lower() == "true",
        "replicas": int(os.getenv("REPLICAS", "1")),
    }
    return DeploymentRequest(**payload)


async def _log_to_stdout(message: str) -> None:
    print(message, flush=True)


async def main() -> int:
    mode = os.getenv("DEPLOY_MODE", "plan").strip().lower()
    deployment_id = os.getenv("DEPLOYMENT_ID") or None
    request = _request_from_env()
    work_dir = tempfile.mkdtemp(prefix="jenkins_portal_")
    await run_local_deployment(request, work_dir, mode, _log_to_stdout, deployment_id=deployment_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
