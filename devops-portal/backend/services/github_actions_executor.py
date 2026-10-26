"""
Runs a deployment on GitHub Actions instead of inside the backend.

Flow:
  1. Seal the user's AWS keys + SSH key pair with PORTAL_WORKFLOW_KEY
     (services/crypto.py) and dispatch portal-deploy.yml with the sealed blob
     as an input. Only the workflow, which has the same key as a repository
     secret, can open it; plaintext secrets never appear in run inputs.
  2. Find the run via its run-name (it embeds the deployment id), log step
     transitions while it runs, then fetch the full job log.
  3. On a successful deploy, look the new instances up in EC2 by their
     PortalDeploymentId tag and record them, so they appear on the Instances
     page and in Prometheus/Grafana. (The runner's own SQLite DB is ephemeral.)
"""

import asyncio
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from models.schemas import DeploymentRequest

from services.crypto import decrypt_secret, seal_for_workflow
from services.execution_types import ExecutionResult, LogFn, MetadataFn


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


@dataclass
class GitHubActionsConfig:
    repo: str
    token: str
    workflow: str = "portal-deploy.yml"
    ref: str = "main"
    api_url: str = "https://api.github.com"
    poll_interval_seconds: int = 5
    request_timeout_seconds: int = 30
    run_discovery_timeout_seconds: int = 120

    @classmethod
    def from_env(cls) -> "GitHubActionsConfig":
        repo = os.getenv("GITHUB_REPO", "").strip("/")
        token = os.getenv("GITHUB_TOKEN", "")
        missing = [
            name for name, value in (("GITHUB_REPO", repo), ("GITHUB_TOKEN", token)) if not value
        ]
        if missing:
            raise RuntimeError(
                f"Missing GitHub Actions configuration: {', '.join(missing)}"
            )

        return cls(
            repo=repo,
            token=token,
            workflow=os.getenv("GITHUB_WORKFLOW", "portal-deploy.yml"),
            ref=os.getenv("GITHUB_REF_NAME", "main"),
            api_url=os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
            poll_interval_seconds=int(os.getenv("GITHUB_POLL_INTERVAL_SECONDS", "5")),
            request_timeout_seconds=int(
                os.getenv("GITHUB_REQUEST_TIMEOUT_SECONDS", "30")
            ),
        )


def _headers(config: GitHubActionsConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "devops-portal",
    }


def _request(
    config: GitHubActionsConfig,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> bytes:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = _headers(config)
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{config.api_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(
            request, timeout=config.request_timeout_seconds
        ) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {detail}")


def _request_json(config: GitHubActionsConfig, path: str) -> dict[str, Any]:
    return json.loads(_request(config, path).decode("utf-8"))


def _seal_credentials(credential: dict | None, request: DeploymentRequest) -> str:
    """Encrypt everything secret the workflow needs into one opaque input."""
    if not credential:
        raise RuntimeError(
            "GitHub Actions deployments need stored AWS credentials - add them "
            "on the Credentials page."
        )
    return seal_for_workflow(
        {
            "aws_access_key_id": credential["access_key_id"],
            "aws_secret_access_key": decrypt_secret(credential["secret_access_key_enc"]),
            "ssh_private_key": decrypt_secret(credential.get("ssh_private_key_enc")) or "",
            "ssh_public_key": request.ssh_public_key or "",
        }
    )


def _dispatch(
    config: GitHubActionsConfig,
    deployment_id: str,
    request: DeploymentRequest,
    mode: str,
    sealed_credentials: str,
) -> None:
    # Keep this list in sync with the `inputs:` block of portal-deploy.yml.
    inputs = {
        "credentials_blob": sealed_credentials,
        "name": request.name or "",
        "detailed_monitoring": "true" if request.detailed_monitoring else "false",
        "deploy_mode": mode,
        "deployment_id": deployment_id,
        "provider": request.provider,
        "region": request.region,
        "instance_type": request.instance_type,
        "instance_count": str(request.instances),
        "key_pair_name": request.key_pair_name,
        "security_group_ports_json": json.dumps(request.security_group_ports),
        "os_type": request.os_type,
        "packages_json": json.dumps(request.packages),
        "custom_commands": request.custom_commands,
        "docker_image": request.docker_image or "",
    }
    _request(
        config,
        f"/repos/{config.repo}/actions/workflows/{config.workflow}/dispatches",
        method="POST",
        body={"ref": config.ref, "inputs": inputs},
    )


def _find_run(config: GitHubActionsConfig, deployment_id: str) -> dict[str, Any] | None:
    # workflow_dispatch returns no run id; the workflow's run-name embeds the
    # deployment id, so match on that.
    data = _request_json(
        config,
        f"/repos/{config.repo}/actions/workflows/{config.workflow}/runs"
        f"?event=workflow_dispatch&per_page=20",
    )
    needle = f"portal-{deployment_id}"
    for run in data.get("workflow_runs", []):
        if needle in (run.get("display_title") or run.get("name") or ""):
            return run
    return None


async def _wait_for_run(
    config: GitHubActionsConfig, deployment_id: str
) -> dict[str, Any]:
    deadline = time.monotonic() + config.run_discovery_timeout_seconds
    while time.monotonic() < deadline:
        run = await asyncio.to_thread(_find_run, config, deployment_id)
        if run:
            return run
        await asyncio.sleep(config.poll_interval_seconds)
    raise RuntimeError("Timed out waiting for GitHub Actions to start the workflow run.")


async def _watch_run(
    config: GitHubActionsConfig, run_id: int, log: LogFn
) -> dict[str, Any]:
    """Poll the run, logging job/step transitions until it completes."""
    seen: dict[str, str] = {}
    while True:
        run = await asyncio.to_thread(
            _request_json, config, f"/repos/{config.repo}/actions/runs/{run_id}"
        )
        jobs = await asyncio.to_thread(
            _request_json,
            config,
            f"/repos/{config.repo}/actions/runs/{run_id}/jobs",
        )
        for job in jobs.get("jobs", []):
            for step in job.get("steps", []):
                key = f"{job['id']}:{step['number']}"
                state = step.get("conclusion") or step.get("status") or ""
                if seen.get(key) != state:
                    seen[key] = state
                    await log(f"[GITHUB] {step['name']}: {state}")

        if run.get("status") == "completed":
            return run
        await asyncio.sleep(config.poll_interval_seconds)


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _download_logs(config: GitHubActionsConfig, run_id: int) -> list[str]:
    raw = _request(config, f"/repos/{config.repo}/actions/runs/{run_id}/logs")
    lines: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        # Top-level entries are one file per job; subdirectory entries are per step.
        for name in sorted(n for n in archive.namelist() if "/" not in n):
            text = archive.read(name).decode("utf-8", errors="replace")
            lines.extend(_ANSI.sub("", line) for line in text.splitlines())
    return lines


async def run_github_actions_deployment(
    deployment_id: str,
    request: DeploymentRequest,
    mode: str,
    log: LogFn,
    update_metadata: MetadataFn,
    credential: dict | None = None,
) -> ExecutionResult:
    config = GitHubActionsConfig.from_env()
    sealed = _seal_credentials(credential, request)
    await log(
        f"[{_ts()}] Dispatching workflow '{config.workflow}' on {config.repo} "
        f"for deployment {deployment_id}"
    )
    await asyncio.to_thread(_dispatch, config, deployment_id, request, mode, sealed)

    run = await _wait_for_run(config, deployment_id)
    run_id = int(run["id"])
    run_url = str(run["html_url"])
    await log(f"[{_ts()}] GitHub run #{run.get('run_number')}: {run_url}")
    await update_metadata(str(run_id), run_url)

    run = await _watch_run(config, run_id, log)

    # Step output is only available as an archive once the run has finished.
    try:
        for line in await asyncio.to_thread(_download_logs, config, run_id):
            await log(f"[GITHUB] {line}")
    except Exception as exc:  # logs are best-effort; the conclusion still decides
        await log(f"[{_ts()}] Could not fetch run logs: {exc}")

    conclusion = run.get("conclusion")
    if conclusion != "success":
        raise RuntimeError(
            f"GitHub Actions run {run_id} finished with conclusion {conclusion}."
        )

    await log(f"[{_ts()}] GitHub Actions run {run_id} completed successfully")

    if mode == "deploy":
        # Imported lazily to avoid a circular import at module load.
        from services.aws_reconciler import sync_deployment_instances

        found = await sync_deployment_instances(deployment_id, request, credential)
        await log(
            f"[{_ts()}] Registered {len(found)} instance(s) from EC2 tag "
            f"PortalDeploymentId={deployment_id}"
        )

    return ExecutionResult(
        status="success",
        execution_mode="github_actions",
        external_ref=str(run_id),
        external_url=run_url,
    )
