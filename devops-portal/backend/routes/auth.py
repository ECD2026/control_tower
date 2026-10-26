"""
Authentication routes:
  POST /api/auth/register  - create an account and start a session
  POST /api/auth/login     - start a session (sets the HttpOnly cookie)
  POST /api/auth/logout    - clear the session cookie
  GET  /api/auth/me        - current user
  GET  /api/auth/verify    - 200/401 probe used by nginx auth_request for
                             /grafana/ and /prometheus/
"""

import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from database.db import create_user, get_user_by_email, list_users_count
from services.auth import (
    clear_session_cookie,
    create_token,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=256)


def _normalise_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    return email


def _signup_allowed() -> bool:
    # PORTAL_ALLOW_SIGNUP: "true" (anyone), "false" (nobody), or "first"
    # (only until the first account exists - handy for a single-team install).
    mode = os.getenv("PORTAL_ALLOW_SIGNUP", "true").strip().lower()
    if mode == "first":
        return list_users_count() == 0
    return mode != "false"


@router.post("/auth/register")
async def register(body: Credentials, response: Response):
    if not _signup_allowed():
        raise HTTPException(status_code=403, detail="Sign-up is disabled on this portal.")
    email = _normalise_email(body.email)
    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user_id = str(uuid.uuid4())
    create_user(user_id, email, hash_password(body.password))
    set_session_cookie(response, create_token(user_id))
    return {"id": user_id, "email": email}


@router.post("/auth/login")
async def login(body: Credentials, response: Response):
    email = _normalise_email(body.email)
    user = get_user_by_email(email)
    # Same message for unknown email and wrong password to avoid user enumeration.
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    set_session_cookie(response, create_token(user["id"]))
    return {"id": user["id"], "email": user["email"]}


@router.post("/auth/logout")
async def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.get("/auth/verify")
async def verify(user: dict = Depends(get_current_user)):
    # Body is ignored by nginx; only the status code matters.
    return Response(status_code=204, headers={"X-Portal-User": user["id"]})
