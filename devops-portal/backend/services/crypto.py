"""
Symmetric encryption helpers for secrets the portal has to hold on to.

Two independent Fernet keys are used so that a leak of one does not expose
the other:

  PORTAL_ENCRYPTION_KEY  - encrypts secrets at rest in SQLite (AWS secret
                           access keys, SSH private keys). Only the portal
                           backend and the CloudWatch exporter know it.
  PORTAL_WORKFLOW_KEY    - seals the per-deployment credential bundle that is
                           handed to the GitHub Actions workflow as a
                           workflow_dispatch input. The same value is stored
                           as the `PORTAL_WORKFLOW_KEY` repository secret, so
                           only the workflow can open the bundle.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import json
import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _key_dir() -> Path:
    # Keep auto-generated keys next to the database so they live on the same
    # persistent volume (/data in docker-compose) and survive container rebuilds.
    db_path = Path(os.getenv("DB_PATH", "deployments.db")).resolve()
    return db_path.parent


def load_or_create_secret(env_name: str, filename: str, generator) -> str:
    """
    Return the secret from `env_name`, or fall back to a file in the data
    directory, generating it on first use. The fallback keeps local
    development friction-free; production should always set the env var.
    """
    value = os.getenv(env_name, "").strip()
    if value:
        return value

    path = _key_dir() / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()

    value = generator()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # chmod is a no-op on some filesystems (e.g. NTFS)
    logger.warning(
        "%s is not set; generated one at %s. Set it explicitly in production.",
        env_name,
        path,
    )
    return value


@lru_cache(maxsize=1)
def _storage_fernet() -> Fernet:
    key = load_or_create_secret(
        "PORTAL_ENCRYPTION_KEY",
        ".portal_encryption_key",
        lambda: Fernet.generate_key().decode(),
    )
    return Fernet(key.encode())


@lru_cache(maxsize=1)
def _workflow_fernet() -> Fernet:
    # No auto-generation here: the value must match the GitHub secret, so a
    # silently generated key would only produce undecryptable bundles.
    key = os.getenv("PORTAL_WORKFLOW_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "PORTAL_WORKFLOW_KEY is not set. It must match the "
            "PORTAL_WORKFLOW_KEY secret configured on the GitHub repository."
        )
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage in the database."""
    return _storage_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str | None) -> str | None:
    """Decrypt a value produced by encrypt_secret. Returns None for empty input."""
    if not token:
        return None
    try:
        return _storage_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored secret could not be decrypted - PORTAL_ENCRYPTION_KEY "
            "has changed since it was saved."
        ) from exc


def seal_for_workflow(payload: dict) -> str:
    """Encrypt a JSON payload so only the GitHub Actions workflow can read it."""
    return _workflow_fernet().encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")


def open_workflow_bundle(token: str, key: str) -> dict:
    """Inverse of seal_for_workflow; used inside the workflow runner."""
    return json.loads(Fernet(key.encode()).decrypt(token.encode("ascii")))


def random_token(nbytes: int = 48) -> str:
    return secrets.token_urlsafe(nbytes)
