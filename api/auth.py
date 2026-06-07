"""Web auth: user store, login route, and role guards. Credentials are verified against the
`users` collection, a short-lived HS256 session token is issued, and protected endpoints are
gated by role. SESSION_SECRET (env) signs/verifies tokens — it is never returned to clients
or logged. The dashboard holds the token in an httpOnly cookie and forwards it as a bearer."""

import os
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from controller.auth import (
    Identity,
    TokenError,
    hash_password,
    make_session_token,
    read_session_token,
    verify_password,
)

ROLE_USER = "user"
ROLE_DBRE = "dbre"
VALID_ROLES = (ROLE_USER, ROLE_DBRE)

# Equalises login timing whether or not the username exists (reduces enumeration signal).
_DUMMY_HASH = hash_password("\x00 absent-account placeholder \x00")


@dataclass(frozen=True)
class UserRecord:
    username: str
    display_name: str
    role: str
    password_hash: str


class AuthStore(Protocol):
    def get_user(self, username: str) -> UserRecord | None: ...


class MongoUserStore:
    def __init__(self, collection) -> None:
        self._col = collection

    def get_user(self, username: str) -> UserRecord | None:
        doc = self._col.find_one({"username": username}, {"_id": False})
        if not doc:
            return None
        return UserRecord(
            username=doc["username"],
            display_name=doc.get("display_name", doc["username"]),
            role=doc["role"],
            password_hash=doc["password_hash"],
        )


def get_auth_store() -> AuthStore:
    raise HTTPException(status_code=503, detail="authentication is not configured")


AuthStoreDep = Annotated[AuthStore, Depends(get_auth_store)]


def session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="SESSION_SECRET is not configured")
    return secret


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    username: str
    display_name: str


auth_router = APIRouter()


@auth_router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, store: AuthStoreDep) -> LoginResponse:
    user = store.get_user(body.username)
    # Always run a hash verification so the response time does not reveal whether the
    # username exists. compare_digest inside verify_password keeps this constant-time.
    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    identity = Identity(username=user.username, display_name=user.display_name, role=user.role)
    token = make_session_token(identity, session_secret())
    return LoginResponse(
        token=token, role=user.role, username=user.username, display_name=user.display_name
    )


def _identity_from_authorization(authorization: str | None) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return read_session_token(token, session_secret())
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="invalid session token") from exc


def require_role(*roles: str):
    """FastAPI dependency factory: returns the verified Identity, or 401 (no/invalid token) /
    403 (role not permitted). With no roles given, any valid session passes."""
    allowed = roles or VALID_ROLES

    def _dependency(authorization: Annotated[str | None, Header()] = None) -> Identity:
        identity = _identity_from_authorization(authorization)
        if identity.role not in allowed:
            raise HTTPException(status_code=403, detail="insufficient role")
        return identity

    return _dependency


def optional_dbre_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> Identity | None:
    """DBRE role guard that is active only when SESSION_SECRET is configured — mirrors
    require_write_token's conditional gating, so local/CI flows stay open while production
    enforces the role. Returns the verified DBRE identity, or None when auth is unconfigured."""
    if not os.environ.get("SESSION_SECRET"):
        return None
    identity = _identity_from_authorization(authorization)
    if identity.role != ROLE_DBRE:
        raise HTTPException(status_code=403, detail="DBRE role required")
    return identity
