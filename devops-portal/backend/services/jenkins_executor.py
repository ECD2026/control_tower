import asyncio
import base64
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from models.schemas import DeploymentRequest

from services.execution_types import ExecutionResult, LogFn, MetadataFn


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


@dataclass
class JenkinsConfig:
    base_url: str
    job_name: str
    user: str
    api_token: str
    verify_tls: bool = True
    poll_interval_seconds: int = 3
    request_timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> "JenkinsConfig":
        base_url = os.getenv("JENKINS_BASE_URL", "").rstrip("/")
        job_name = os.getenv("JENKINS_JOB_NAME", "").strip("/")
        user = os.getenv("JENKINS_USER", "")
        api_token = os.getenv("JENKINS_API_TOKEN", "")
        verify_tls = os.getenv("JENKINS_VERIFY_TLS", "true").lower() != "false"
        poll_interval_seconds = int(os.getenv("JENKINS_POLL_INTERVAL_SECONDS", "3"))
        request_timeout_seconds = int(
            os.getenv("JENKINS_REQUEST_TIMEOUT_SECONDS", "15")
        )

        missing = [
            name
            for name, value in (
                ("JENKINS_BASE_URL", base_url),
                ("JENKINS_JOB_NAME", job_name),
                ("JENKINS_USER", user),
                ("JENKINS_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            missing_list = ", ".join(missing)
            raise RuntimeError(f"Missing Jenkins configuration: {missing_list}")

        return cls(
            base_url=base_url,
            job_name=job_name,
            user=user,
            api_token=api_token,
            verify_tls=verify_tls,
            poll_interval_seconds=poll_interval_seconds,
            request_timeout_seconds=request_timeout_seconds,
        )

    @property
    def context(self) -> ssl.SSLContext | None:
        if self.verify_tls:
            return None
        return ssl._create_unverified_context()


def _job_path(job_name: str) -> str:
    segments = [segment for segment in job_name.split("/") if segment]
    return "/".join(f"job/{urllib.parse.quote(segment)}" for segment in segments)


def _build_headers(config: JenkinsConfig) -> dict[str, str]:
    token = base64.b64encode(
        f"{config.user}:{config.api_token}".encode("utf-8")
    ).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _full_url(config: JenkinsConfig, path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    if path_or_url.startswith("/"):
        return f"{config.base_url}{path_or_url}"
    return f"{config.base_url}/{path_or_url}"


def _request_json(
    config: JenkinsConfig,
    path: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = _full_url(config, path)
    request_headers = _build_headers(config)
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(url, headers=request_headers, method="GET")
    with urllib.request.urlopen(
        request,
        timeout=config.request_timeout_seconds,
        context=config.context,
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_text(
    config: JenkinsConfig,
    path: str,
    headers: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    url = _full_url(config, path)
    request_headers = _build_headers(config)
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(url, headers=request_headers, method="GET")
    with urllib.request.urlopen(
        request,
        timeout=config.request_timeout_seconds,
        context=config.context,
    ) as response:
        text = response.read().decode("utf-8", errors="replace")
        return text, dict(response.headers.items())


def _get_crumb_headers(config: JenkinsConfig) -> dict[str, str]:
    try:
        data = _request_json(config, "/crumbIssuer/api/json")
        field = data.get("crumbRequestField")
        crumb = data.get("crumb")
        if field and crumb:
            return {field: crumb}
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 405):
            raise
    except urllib.error.URLError:
        raise
    return {}


def _post_form(
    config: JenkinsConfig,
    path: str,
    form_data: dict[str, str],
) -> dict[str, str]:
    url = _full_url(config, path)
    headers = _build_headers(config)
    headers.update(_get_crumb_headers(config))
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    payload = urllib.parse.urlencode(form_data).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(
        request,
        timeout=config.request_timeout_seconds,
        context=config.context,
    ) as response:
        return dict(response.headers.items())


def _start_build(
    config: JenkinsConfig,
    deployment_id: str,
    request: DeploymentRequest,
    mode: str,
) -> str:
    path = f"/{_job_path(config.job_name)}/buildWithParameters"
    form_data = {
        "DEPLOYMENT_ID": deployment_id,
        "DEPLOY_MODE": mode,
        "PROVIDER": request.provider,
        "REGION": request.region,
        "INSTANCE_TYPE": request.instance_type,
        "INSTANCE_COUNT": str(request.instances),
        "KEY_PAIR_NAME": request.key_pair_name,
        "SECURITY_GROUP_PORTS_JSON": json.dumps(request.security_group_ports),
        "OS_TYPE": request.os_type,
        "PACKAGES_JSON": json.dumps(request.packages),
        "CUSTOM_COMMANDS": request.custom_commands,
        "DOCKER_IMAGE": request.docker_image or "",
        "KUBERNETES": "true" if request.kubernetes else "false",
        "REPLICAS": str(request.replicas),
    }
    headers = _post_form(config, path, form_data)
    queue_url = headers.get("Location")
    if not queue_url:
        raise RuntimeError("Jenkins did not return a queue location for the build.")
    return queue_url.rstrip("/")


async def _poll_queue_until_build(
    config: JenkinsConfig,
    queue_url: str,
    log: LogFn,
) -> tuple[str, str]:
    while True:
        data = await asyncio.to_thread(_request_json, config, f"{queue_url}/api/json")
        executable = data.get("executable") or {}
        if executable.get("number") is not None and executable.get("url"):
            build_number = str(executable["number"])
            build_url = str(executable["url"]).rstrip("/")
            await log(
                f"[{_ts()}] Jenkins assigned build #{build_number}: {build_url}"
            )
            return build_number, build_url

        if data.get("cancelled"):
            raise RuntimeError("Jenkins queue item was cancelled before execution.")

        await asyncio.sleep(config.poll_interval_seconds)


async def _stream_console_until_complete(
    config: JenkinsConfig,
    build_url: str,
    log: LogFn,
) -> str:
    offset = 0
    last_result = "UNKNOWN"

    while True:
        log_path = f"{build_url}/logText/progressiveText?start={offset}"
        text, headers = await asyncio.to_thread(_request_text, config, log_path)

        if text:
            for line in text.splitlines():
                await log(f"[JENKINS] {line}")

        try:
            offset = int(headers.get("X-Text-Size", offset))
        except ValueError:
            pass

        build_info = await asyncio.to_thread(
            _request_json,
            config,
            f"{build_url}/api/json",
        )
        last_result = build_info.get("result") or "RUNNING"

        more_data = headers.get("X-More-Data", "false").lower() == "true"
        if not build_info.get("building") and not more_data:
            return last_result

        await asyncio.sleep(config.poll_interval_seconds)


async def run_jenkins_deployment(
    deployment_id: str,
    request: DeploymentRequest,
    mode: str,
    log: LogFn,
    update_metadata: MetadataFn,
) -> ExecutionResult:
    config = JenkinsConfig.from_env()
    await log(
        f"[{_ts()}] Triggering Jenkins job '{config.job_name}' for deployment "
        f"{deployment_id}"
    )
    queue_url = await asyncio.to_thread(_start_build, config, deployment_id, request, mode)
    await log(f"[{_ts()}] Jenkins queue item created: {queue_url}")
    await update_metadata(queue_url, queue_url)

    build_number, build_url = await _poll_queue_until_build(config, queue_url, log)
    await update_metadata(build_number, build_url)

    result = await _stream_console_until_complete(config, build_url, log)
    if result != "SUCCESS":
        raise RuntimeError(
            f"Jenkins build #{build_number} finished with result {result}."
        )

    await log(f"[{_ts()}] Jenkins build #{build_number} completed successfully")
    return ExecutionResult(
        status="success",
        execution_mode="jenkins",
        external_ref=build_number,
        external_url=build_url,
    )
