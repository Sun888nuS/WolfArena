"""Password, token, hashing, and cookie helpers."""

from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Response

from app.config import Settings

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches an Argon2 hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(user_id: UUID, settings: Settings) -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.auth_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> UUID | None:
    """Decode an access token and return its subject user id."""
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
        subject = payload.get("sub")
        if not isinstance(subject, str):
            return None
        return UUID(subject)
    except (jwt.PyJWTError, ValueError):
        return None


def create_refresh_token() -> str:
    """Create an opaque high-entropy refresh token."""
    return secrets.token_urlsafe(48) #secrets 模块中用于生成安全随机 Token 的函数，48 字节的随机数


def hash_token(token: str) -> str:
    """Hash an opaque token before persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    settings: Settings,
) -> None:
    """Set HttpOnly auth cookies on the response."""
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=settings.auth_access_token_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.auth_refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/api/auth",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    """Clear auth cookies from the browser."""
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/api/auth",
    )
