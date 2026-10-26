"""
GitHub Actions helper: open the sealed credential bundle sent by the portal.

Inputs (environment):
  PORTAL_CREDENTIALS_BLOB  - the `credentials_blob` workflow_dispatch input
  PORTAL_WORKFLOW_KEY      - repository secret with the matching Fernet key
  KEY_PAIR_NAME            - used to name the private key file

Effects:
  - registers every secret value with `::add-mask::` so it is redacted from
    all later log output,
  - exports AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / SSH_PUBLIC_KEY via
    $GITHUB_ENV for the following steps,
  - writes the private key to ~/.ssh/<KEY_PAIR_NAME>.pem with mode 0600
    (where run_local_deployment looks for it by default).
"""

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.crypto import open_workflow_bundle  # noqa: E402


def main() -> int:
    blob = os.environ.get("PORTAL_CREDENTIALS_BLOB", "").strip()
    key = os.environ.get("PORTAL_WORKFLOW_KEY", "").strip()
    key_pair_name = os.environ.get("KEY_PAIR_NAME", "portal").strip() or "portal"
    if not blob or not key:
        print("::error::credentials_blob input or PORTAL_WORKFLOW_KEY secret is missing")
        return 1

    try:
        bundle = open_workflow_bundle(blob, key)
    except Exception:
        print("::error::Could not decrypt credentials_blob - PORTAL_WORKFLOW_KEY "
              "on GitHub must match the portal's PORTAL_WORKFLOW_KEY.")
        return 1

    secret = bundle["aws_secret_access_key"]
    private_key = bundle.get("ssh_private_key", "")
    print(f"::add-mask::{bundle['aws_access_key_id']}")
    print(f"::add-mask::{secret}")
    for line in private_key.splitlines():
        if line.strip() and "PRIVATE KEY" not in line:
            print(f"::add-mask::{line.strip()}")

    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
        env.write(f"AWS_ACCESS_KEY_ID={bundle['aws_access_key_id']}\n")
        env.write(f"AWS_SECRET_ACCESS_KEY={secret}\n")
        env.write(f"SSH_PUBLIC_KEY={bundle.get('ssh_public_key', '')}\n")

    if private_key:
        ssh_dir = Path.home() / ".ssh"
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        key_path = ssh_dir / f"{key_pair_name}.pem"
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(private_key.strip() + "\n")

    print("Credential bundle opened; secrets are masked for the rest of the job.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
