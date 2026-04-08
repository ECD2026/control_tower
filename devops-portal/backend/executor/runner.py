"""
Async subprocess execution helper.

asyncio.create_subprocess_exec does NOT work on Windows SelectorEventLoop
(which uvicorn uses). Instead we run the process in a thread via
asyncio.to_thread and stream lines through an asyncio.Queue.
"""

import asyncio
import os
import queue
import shutil
import subprocess
import threading
from typing import AsyncGenerator


def _resolve_command(cmd_name: str) -> str:
    """Resolve a command to its full path."""
    # Hard-coded known locations first
    known_paths = {
        "terraform": r"C:\Users\Asus\develop\terraform\terraform.exe",
        "ansible-playbook": (
            r"C:\Users\Asus\AppData\Local\Programs\Python"
            r"\Python312\Scripts\ansible-playbook.exe"
        ),
    }
    if cmd_name in known_paths:
        path = known_paths[cmd_name]
        if os.path.exists(path):
            return path

    # Fall back to PATH search
    found = shutil.which(cmd_name)
    return found if found else cmd_name


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
    if extra_env:
        env.update(extra_env)

    resolved_cmd = [_resolve_command(cmd[0])] + cmd[1:]

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
