"""
Authentication primitives for the portal.

- Passwords are hashed with scrypt (stdlib hashlib) and a per-user salt.
- Sessions are stateless HS256 JWTs. The browser receives the token in an
  HttpOnly cookie so it is never readable from JavaScript; API clients such as
  curl can send the same token as `Authorization: Bearer <token>`.
- nginx calls GET /api/auth/verify (auth_request) before proxying /grafana/
  and /prometheus/, so the monitoring UIs are only reachable when logged in.
"""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, Response

from database.db import get_user
from services.crypto import load_or_create_secret, random_token

COOKIE_NAME = "portal_session"
TOKEN_TTL_HOURS = int(os.getenv("PORTAL_SESSION_HOURS", "12"))
JWT_ALGORITHM = "HS256"

# scrypt cost parameters (~16 MiB of memory per hash).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _jwt_secret() -> str:
    return load_or_create_secret("PORTAL_JWT_SECRET", ".portal_jwt_secret", random_token)


# ---------- Passwords ----------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=base64.b64decode(salt_b64),
        n=int(n),
        r=int(r),
        p=int(p),
    )
    return hmac.compare_digest(candidate, base64.b64decode(digest_b64))


# ---------- Tokens / cookies ----------


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=TOKEN_TTL_HOURS)}
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_HOURS * 3600,
        httponly=True,
        # Lax blocks the cookie on cross-site POSTs, which is our CSRF defence.
        samesite="lax",
        # Enable once the portal is served over HTTPS.
        secure=os.getenv("PORTAL_COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def get_current_user(request: Request) -> dict:
    """FastAPI dependency: resolve the logged-in user or raise 401."""
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    user = get_user(payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}
