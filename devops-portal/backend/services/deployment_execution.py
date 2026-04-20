import os

from models.schemas import DeploymentRequest

from services.execution_types import ExecutionResult, LogFn, MetadataFn
from services.jenkins_executor import run_jenkins_deployment
from services.local_executor import run_local_deployment


def get_execution_mode() -> str:
    mode = os.getenv("DEPLOYMENT_RUNNER_MODE", "local").strip().lower()
    if mode not in {"local", "jenkins"}:
        return "local"
    return mode


async def run_requested_deployment(
    deployment_id: str,
    request: DeploymentRequest,
    work_dir: str,
    mode: str,
    log: LogFn,
    update_metadata: MetadataFn,
) -> ExecutionResult:
    execution_mode = get_execution_mode()
    if execution_mode == "jenkins":
        return await run_jenkins_deployment(
            deployment_id=deployment_id,
            request=request,
            mode=mode,
            log=log,
            update_metadata=update_metadata,
        )

    return await run_local_deployment(
        request=request,
        work_dir=work_dir,
        mode=mode,
        log=log,
        deployment_id=deployment_id,
    )
