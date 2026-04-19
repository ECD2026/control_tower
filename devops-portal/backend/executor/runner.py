"""
Async subprocess execution helper.

asyncio.create_subprocess_exec does NOT work on Windows SelectorEventLoop
(which uvicorn uses). Instead we run the process in a thread via
asyncio.to_thread and stream lines through an asyncio.Queue.
"""

import asyncio
import os
import queue
import sys
import shutil
import subprocess
import threading
from typing import AsyncGenerator


TERRAFORM_EXE = r"C:\Users\Asus\develop\terraform\terraform.exe"

# Ansible is NOT supported on Windows as a control node (os.get_blocking fails).
# Route all Ansible commands through WSL (Ubuntu) which has ansible installed
# and a proper UTF-8 locale.
WSL_EXE = r"C:\Windows\System32\wsl.exe"


def _win_to_wsl(path: str) -> str:
    """Convert a Windows path to its WSL /mnt/... equivalent."""
    # e.g. C:\Users\Asus\Temp\foo.ini → /mnt/c/Users/Asus/Temp/foo.ini
    path = path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        path = f"/mnt/{drive}{path[2:]}"
    return path


def _resolve_command(cmd: list[str]) -> list[str]:
    """
    Resolve a command list to its full invocation.

    - terraform      → Windows .exe (works fine natively)
    - ansible-*      → WSL ansible-playbook (avoids Windows locale / blocking-IO issues)
    """
    name = cmd[0]

    if name == "terraform":
        exe = (
            TERRAFORM_EXE
            if os.path.exists(TERRAFORM_EXE)
            else shutil.which("terraform") or "terraform"
        )
        return [exe] + cmd[1:]

    if name == "ansible-playbook":
        if sys.platform == "win32":
            # Convert every Windows path argument to a WSL path
            wsl_args = []
            for arg in cmd[1:]:
                if len(arg) >= 3 and arg[1] == ":" and arg[2] in ("\\/"):
                    wsl_args.append(_win_to_wsl(arg))
                else:
                    wsl_args.append(arg)
            return [WSL_EXE, "--", "ansible-playbook"] + wsl_args

        found = shutil.which("ansible-playbook")
        return [found or "ansible-playbook"] + cmd[1:]

    # Generic fallback
    found = shutil.which(name)
    return [found or name] + cmd[1:]


def _stream_process(cmd: list[str], cwd: str, env: dict, line_queue: queue.Queue) -> int:
    """
    Run *cmd* synchronously in a thread.
    Each output line is put into *line_queue*.
    Sentinel None is put when done.
    Returns the process exit code.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout:
        line_queue.put(line.rstrip())
    proc.wait()
    return proc.returncode


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
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    # Force UTF-8 so Ansible doesn't fail on Windows-1252 locale
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LC_ALL"] = "en_US.UTF-8"
    if extra_env:
        env.update(extra_env)

    resolved_cmd = _resolve_command(cmd)

    # Thread-safe queue to bridge the sync subprocess thread and async caller
    line_queue: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()

    # Start the blocking subprocess in a thread pool
    future = loop.run_in_executor(
        None, _stream_process, resolved_cmd, cwd, env, line_queue
    )

    # Keep recent lines to provide actionable context on failures.
    recent_lines: list[str] = []

    # Drain the queue while the thread is still running
    while True:
        try:
            line = line_queue.get_nowait()
            recent_lines.append(line)
            if len(recent_lines) > 40:
                recent_lines.pop(0)
            yield line
        except queue.Empty:
            if future.done():
                # Thread finished — drain any remaining lines
                while True:
                    try:
                        line = line_queue.get_nowait()
                        recent_lines.append(line)
                        if len(recent_lines) > 40:
                            recent_lines.pop(0)
                        yield line
                    except queue.Empty:
                        break
                break
            # Give the subprocess thread a moment to produce output
            await asyncio.sleep(0.05)

    returncode = await future
    if returncode != 0:
        tail = "\n".join(recent_lines[-10:]).strip()
        detail = f"\nLast output lines:\n{tail}" if tail else ""
        raise RuntimeError(
            f"Command `{' '.join(cmd)}` exited with code {returncode}{detail}"
        )
