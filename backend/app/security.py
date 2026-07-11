from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings


class UserRole(str, Enum):
    outlet_operator = "OUTLET_OPERATOR"
    area_manager = "AREA_MANAGER"
    central_operations = "CENTRAL_OPERATIONS"
    risk_reviewer = "RISK_REVIEWER"
    admin = "ADMIN"


class TokenRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=200, repr=False)


class AuthenticatedUser(BaseModel):
    username: str
    display_name: str
    role: UserRole
    outlet_ids: list[str] = Field(default_factory=list)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthenticatedUser


@dataclass(frozen=True)
class _DemoUser:
    username: str
    display_name: str
    role: UserRole
    outlet_ids: tuple[str, ...]
    password_hash: str


def _hash_password(password: str, salt: str, iterations: int = 210_000) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, expected_digest)


def _demo_user(
    username: str,
    password: str,
    display_name: str,
    role: UserRole,
    outlet_ids: tuple[str, ...] = ("AGT-SYL-017",),
) -> _DemoUser:
    salt = f"superagent-demo-{username}"
    return _DemoUser(
        username=username,
        display_name=display_name,
        role=role,
        outlet_ids=outlet_ids,
        password_hash=_hash_password(password, salt),
    )


_DEMO_USERS: dict[str, _DemoUser] = {
    "operator@sentinel.local": _demo_user(
        "operator@sentinel.local",
        "operator-demo-pass",
        "Demo Outlet Operator",
        UserRole.outlet_operator,
    ),
    "manager@sentinel.local": _demo_user(
        "manager@sentinel.local",
        "manager-demo-pass",
        "Demo Area Manager",
        UserRole.area_manager,
    ),
    "ops@sentinel.local": _demo_user(
        "ops@sentinel.local",
        "ops-demo-pass",
        "Demo Central Operations",
        UserRole.central_operations,
    ),
    "risk@sentinel.local": _demo_user(
        "risk@sentinel.local",
        "risk-demo-pass",
        "Demo Risk Reviewer",
        UserRole.risk_reviewer,
    ),
    "admin@sentinel.local": _demo_user(
        "admin@sentinel.local",
        "admin-demo-pass",
        "Demo Admin",
        UserRole.admin,
        ("AGT-SYL-017", "*"),
    ),
}


def authenticate_user(username: str, password: str) -> AuthenticatedUser | None:
    key = username.strip().lower()
    record = _DEMO_USERS.get(key)
    if record is None:
        return None

    if not _verify_password(password, record.password_hash):
        return None

    return AuthenticatedUser(
        username=record.username,
        display_name=record.display_name,
        role=record.role,
        outlet_ids=list(record.outlet_ids),
    )


def create_access_token(user: AuthenticatedUser) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    token = jwt.encode(
        {
            "sub": user.username,
            "name": user.display_name,
            "role": user.role.value,
            "outlets": user.outlet_ids,
            "iat": datetime.now(timezone.utc),
            "exp": expires_at,
            "nonce": secrets.token_hex(8),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str) -> AuthenticatedUser:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from exc

    try:
        username = str(payload["sub"])
        display_name = str(payload.get("name") or username)
        role = UserRole(str(payload["role"]))
        outlets_raw = payload.get("outlets") or []
        outlet_ids = [str(value) for value in outlets_raw]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token claims.",
        ) from exc

    return AuthenticatedUser(
        username=username,
        display_name=display_name,
        role=role,
        outlet_ids=outlet_ids,
    )


_bearer = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    token: str | None = None

    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    if token is None:
        token = request.query_params.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    user = decode_access_token(token)
    request.state.user = user
    return user


def require_roles(*roles: UserRole) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    allowed = set(roles)

    async def dependency(
        user: AuthenticatedUser = Depends(current_user),
    ) -> AuthenticatedUser:
        if user.role == UserRole.admin or user.role in allowed:
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user does not have permission for this action.",
        )

    return dependency


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                body_size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid Content-Length header."},
                )

            if body_size > self.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body is too large."},
                )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response
