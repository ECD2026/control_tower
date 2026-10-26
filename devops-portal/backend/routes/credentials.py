"""
AWS credential + SSH key pair routes (all scoped to the logged-in user):
  GET    /api/credentials                 - list credentials (secrets never returned)
  POST   /api/credentials                 - verify keys with STS and store them
  POST   /api/credentials/{id}/key-pair   - replace / generate the SSH key pair
  DELETE /api/credentials/{id}            - remove a credential

How the key pair is used: the portal stores the private key (encrypted) and
the OpenSSH public key. Each deployment registers the public key in the
target region via a Terraform `aws_key_pair` resource, so a single key pair
works in every region without the user creating it in the EC2 console first.
"""

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database.db import (
    delete_credential,
    get_credential,
    list_credentials,
    list_instances,
    save_credential,
    update_credential_key_pair,
)
from services.auth import get_current_user
from services.aws_clients import (
    generate_ssh_key_pair,
    public_key_from_private,
    verify_access_keys,
)
from services.crypto import encrypt_secret

router = APIRouter()

_KEY_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_ACCESS_KEY_RE = re.compile(r"^(AKIA|ASIA)[A-Z0-9]{12,124}$")


class KeyPairInput(BaseModel):
    key_pair_name: str = Field(description="Logical name, used as the AWS key pair prefix")
    ssh_private_key: Optional[str] = Field(
        default=None, description="Contents of an existing .pem file"
    )
    generate_key_pair: bool = Field(
        default=False, description="Generate a new ed25519 key pair instead of uploading one"
    )


class CredentialInput(KeyPairInput):
    name: str = Field(min_length=1, max_length=64)
    access_key_id: str
    secret_access_key: str = Field(min_length=16)
    default_region: str = "ap-south-1"


def _public_view(row: dict) -> dict:
    """Shape a credential row for the API - secrets are never included."""
    key = row["access_key_id"]
    return {
        "id": row["id"],
        "name": row["name"],
        "access_key_id": f"{key[:4]}{'*' * 8}{key[-4:]}",
        "default_region": row["default_region"],
        "account_id": row.get("account_id"),
        "arn": row.get("arn"),
        "key_pair_name": row.get("key_pair_name"),
        "has_private_key": bool(row.get("ssh_private_key_enc")),
        "ssh_public_key": row.get("ssh_public_key"),
        "created_at": row.get("created_at"),
    }


def _resolve_key_pair(body: KeyPairInput) -> tuple[str, str, Optional[str]]:
    """
    Validate key pair input. Returns (public_key, private_key_enc,
    private_key_to_return). The plaintext private key is only returned when we
    generated it, so the user can download it once.
    """
    if not _KEY_NAME_RE.match(body.key_pair_name):
        raise HTTPException(
            status_code=400,
            detail="Key pair name may only contain letters, digits, '.', '_' and '-'.",
        )
    if body.generate_key_pair:
        private_pem, public_key = generate_ssh_key_pair()
        return public_key, encrypt_secret(private_pem), private_pem
    if not body.ssh_private_key or not body.ssh_private_key.strip():
        raise HTTPException(
            status_code=400,
            detail="Upload the key pair's private key (.pem) or choose to generate one.",
        )
    try:
        public_key = public_key_from_private(body.ssh_private_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return public_key, encrypt_secret(body.ssh_private_key.strip()), None


@router.get("/credentials")
async def get_credentials(user: dict = Depends(get_current_user)):
    return [_public_view(row) for row in list_credentials(user["id"])]


@router.post("/credentials", status_code=201)
async def create_credential(body: CredentialInput, user: dict = Depends(get_current_user)):
    access_key_id = body.access_key_id.strip()
    secret_access_key = body.secret_access_key.strip()
    if not _ACCESS_KEY_RE.match(access_key_id):
        raise HTTPException(status_code=400, detail="That does not look like an AWS access key ID.")

    try:
        identity = verify_access_keys(access_key_id, secret_access_key, body.default_region)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    public_key, private_key_enc, generated_private_key = _resolve_key_pair(body)

    row = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "name": body.name.strip(),
        "access_key_id": access_key_id,
        "secret_access_key_enc": encrypt_secret(secret_access_key),
        "default_region": body.default_region,
        "account_id": identity["account_id"],
        "arn": identity["arn"],
        "key_pair_name": body.key_pair_name,
        "ssh_public_key": public_key,
        "ssh_private_key_enc": private_key_enc,
    }
    save_credential(row)
    saved = get_credential(row["id"], user["id"])
    response = _public_view(saved)
    if generated_private_key:
        response["generated_private_key"] = generated_private_key
    return response


@router.post("/credentials/{credential_id}/key-pair")
async def replace_key_pair(
    credential_id: str,
    body: KeyPairInput,
    user: dict = Depends(get_current_user),
):
    if not get_credential(credential_id, user["id"]):
        raise HTTPException(status_code=404, detail="Credential not found")
    public_key, private_key_enc, generated_private_key = _resolve_key_pair(body)
    update_credential_key_pair(credential_id, body.key_pair_name, public_key, private_key_enc)
    response = _public_view(get_credential(credential_id, user["id"]))
    if generated_private_key:
        response["generated_private_key"] = generated_private_key
    return response


@router.delete("/credentials/{credential_id}")
async def remove_credential(credential_id: str, user: dict = Depends(get_current_user)):
    in_use = [
        inst["id"]
        for inst in list_instances(user_id=user["id"], exclude_terminated=True)
        if inst.get("credential_id") == credential_id
    ]
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                "These instances still use this credential - terminate them first: "
                + ", ".join(in_use)
            ),
        )
    if not delete_credential(credential_id, user["id"]):
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"deleted": credential_id}
