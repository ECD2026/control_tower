"""
Per-user AWS access.

Every AWS call the portal makes on behalf of a user goes through
session_for_credential(), which builds a boto3 session from the credential the
user uploaded on the Credentials page. Nothing falls back to the backend's own
environment unless a row predates credentials (legacy data).
"""

import os
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from services.crypto import decrypt_secret


def _boto3():
    try:
        import boto3

        return boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is not installed in the backend environment. "
            "Run `pip install -r requirements.txt`."
        ) from exc


def session_for_credential(credential: Optional[dict], region: Optional[str] = None):
    """Return a boto3 Session for a stored credential row (decrypting the secret)."""
    boto3 = _boto3()
    region_name = region or (credential or {}).get("default_region") or os.getenv(
        "AWS_DEFAULT_REGION", "us-east-1"
    )
    if not credential:
        # Legacy rows created before per-user credentials: use the default chain.
        return boto3.Session(region_name=region_name)
    return boto3.Session(
        aws_access_key_id=credential["access_key_id"],
        aws_secret_access_key=decrypt_secret(credential["secret_access_key_enc"]),
        region_name=region_name,
    )


def credential_env(credential: dict, region: str) -> dict:
    """Environment variables that make Terraform/AWS CLI act as this credential."""
    return {
        "AWS_ACCESS_KEY_ID": credential["access_key_id"],
        "AWS_SECRET_ACCESS_KEY": decrypt_secret(credential["secret_access_key_enc"]) or "",
        "AWS_DEFAULT_REGION": region,
        "AWS_REGION": region,
    }


def verify_access_keys(access_key_id: str, secret_access_key: str, region: str) -> dict:
    """
    Call STS GetCallerIdentity to prove the keys work before we store them.
    Returns {"account_id", "arn"}; raises ValueError with an AWS message otherwise.
    """
    boto3 = _boto3()
    try:
        sts = boto3.client(
            "sts",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        identity = sts.get_caller_identity()
    except Exception as exc:  # botocore raises many subclasses; surface the message
        raise ValueError(f"AWS rejected these credentials: {exc}") from exc
    return {"account_id": identity["Account"], "arn": identity["Arn"]}


# ---------- SSH key pairs ----------


def generate_ssh_key_pair() -> tuple[str, str]:
    """Generate an ed25519 key pair. Returns (private_pem, openssh_public_key)."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()
    return private_pem, public_key


def public_key_from_private(private_pem: str) -> str:
    """
    Derive the OpenSSH public key from an uploaded private key (.pem from the
    EC2 console, or an OpenSSH key). Raises ValueError for unsupported input.
    """
    data = private_pem.strip().encode()
    loaders = (
        lambda: serialization.load_pem_private_key(data, password=None),
        lambda: serialization.load_ssh_private_key(data, password=None),
    )
    key = None
    for loader in loaders:
        try:
            key = loader()
            break
        except (ValueError, TypeError):
            continue
    if key is None:
        raise ValueError(
            "Could not read the private key. Upload an unencrypted RSA or ED25519 "
            "key (the .pem file AWS gives you when creating a key pair)."
        )
    if not isinstance(key, (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)):
        raise ValueError("Only RSA and ED25519 keys are supported by EC2.")
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()
