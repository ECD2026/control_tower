"""
Async subprocess execution helper.
Streams stdout+stderr line-by-line via an async generator.
"""

import asyncio
import os
from typing import AsyncGenerator


async def execute_command(
    cmd: list[str],
    cwd: str,
    extra_env: dict | None = None,
) -> AsyncGenerator[str, None]:
    """
    Run *cmd* in *cwd* and yield each output line as it arrives.
    Raises RuntimeError if the process exits with a non-zero code.
    """
    env = os.environ.copy()
    # Disable host-key checking so Ansible doesn't hang waiting for input
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    if extra_env:
        env.update(extra_env)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=env,
    )

    assert process.stdout is not None

    while True:
        line = await process.stdout.readline()
        if not line:
            break
        yield line.decode("utf-8", errors="replace").rstrip()

    await process.wait()
    if process.returncode != 0:
        raise RuntimeError(
            f"Command `{' '.join(cmd)}` exited with code {process.returncode}"
        )
