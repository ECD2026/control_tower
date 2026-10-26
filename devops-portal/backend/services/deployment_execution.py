"""
Chooses where a deployment runs, based on DEPLOYMENT_RUNNER_MODE:

  local           - Terraform + Ansible run inside the backend process/container
  github_actions  - the portal dispatches .github/workflows/portal-deploy.yml
                    and streams progress back (services/github_actions_executor.py)
"""

import os

from models.schemas import DeploymentRequest

from services.aws_clients import credential_env
from services.execution_types import ExecutionResult, LogFn, MetadataFn
from services.github_actions_executor import run_github_actions_deployment
from services.local_executor import run_local_deployment
from services.ssh_keys import private_key_file


def get_execution_mode() -> str:
    mode = os.getenv("DEPLOYMENT_RUNNER_MODE", "local").strip().lower()
    if mode not in {"local", "github_actions"}:
        return "local"
    return mode


async def run_requested_deployment(
    deployment_id: str,
    request: DeploymentRequest,
    work_dir: str,
    mode: str,
    log: LogFn,
    update_metadata: MetadataFn,
    credential: dict | None = None,
) -> ExecutionResult:
    execution_mode = get_execution_mode()
    if execution_mode == "github_actions":
        return await run_github_actions_deployment(
            deployment_id=deployment_id,
            request=request,
            mode=mode,
            log=log,
            update_metadata=update_metadata,
            credential=credential,
        )

    # Local mode: hand the user's keys to Terraform via env and write the SSH
    # key to disk only for the lifetime of this job.
    extra_env = credential_env(credential, request.region) if credential else None
    with private_key_file(credential, work_dir) as ssh_key_path:
        return await run_local_deployment(
            request=request,
            work_dir=work_dir,
            mode=mode,
            log=log,
            deployment_id=deployment_id,
            extra_env=extra_env,
            ssh_key_path=ssh_key_path,
        )
