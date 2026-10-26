"""
Temporarily materialise a user's SSH private key on disk for ssh/Ansible.

Keys live encrypted in the database; they are only written out for the
duration of a deployment or configuration job and removed afterwards.

On Linux/macOS the key goes into the job's temp work dir with mode 0600.
On Windows, ssh and Ansible run inside WSL (see executor/runner.py), and WSL
refuses keys on NTFS because chmod has no effect there, so the key is written
into the WSL home directory instead and the WSL path is returned.
"""

import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional

from services.crypto import decrypt_secret

WSL_EXE = r"C:\Windows\System32\wsl.exe"


@contextmanager
def private_key_file(credential: Optional[dict], work_dir: str) -> Iterator[Optional[str]]:
    """
    Yield a path to the credential's private key, or None when the credential
    has no stored key (callers then fall back to SSH_KEY_DIR/<name>.pem).
    """
    pem = decrypt_secret((credential or {}).get("ssh_private_key_enc"))
    if not pem:
        yield None
        return

    pem = pem.strip() + "\n"
    if sys.platform == "win32":
        name = f"portal-{uuid.uuid4().hex[:12]}.pem"
        result = subprocess.run(
            [
                WSL_EXE, "--", "bash", "-c",
                f'umask 077 && mkdir -p ~/.ssh/portal && cat > ~/.ssh/portal/{name} '
                f'&& echo "$HOME/.ssh/portal/{name}"',
            ],
            input=pem,
            capture_output=True,
            text=True,
            check=True,
        )
        wsl_path = result.stdout.strip().splitlines()[-1]
        try:
            yield wsl_path
        finally:
            subprocess.run([WSL_EXE, "--", "rm", "-f", wsl_path], check=False)
        return

    path = os.path.join(work_dir, "portal_key.pem")
    # O_EXCL + 0600 so the key is never briefly world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(pem)
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
