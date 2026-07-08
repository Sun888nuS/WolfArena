"""Authentication service tests."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import Response
import pytest

from app.auth.exceptions import DuplicateEmailError, InvalidCredentialsError
from app.auth.security import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, verify_password
from app.auth.service import AuthService
from app.config import Settings


class FakeRepository:
    """In-memory auth repository for service tests."""

    def __init__(self) -> None:
        self.users: dict[str, SimpleNamespace] = {}
        self.sessions: dict[str, SimpleNamespace] = {}

    async def get_user_by_email(self, email: str):
        return self.users.get(email)

    async def get_user_by_id(self, user_id):
        return next((user for user in self.users.values() if user.id == user_id), None)

    async def create_user(self, *, email, password_hash, display_name, email_verified):
        if email in self.users:
            raise DuplicateEmailError()
        user = SimpleNamespace(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            is_active=True,
            email_verified=email_verified,
            created_at=datetime.now(UTC),
            last_login_at=None,
        )
        self.users[email] = user
        return user

    async def create_session(
        self,
        *,
        user_id,
        refresh_token_hash,
        expires_at,
        user_agent,
        ip_address,
    ):
        session = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            revoked_at=None,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.sessions[refresh_token_hash] = session
        return session

    async def get_active_session_by_refresh_hash(self, refresh_token_hash, *, now):
        session = self.sessions.get(refresh_token_hash)
        if not session or session.revoked_at or session.expires_at <= now:
            return None
        return session

    async def revoke_session(self, session_id):
        for session in self.sessions.values():
            if session.id == session_id:
                session.revoked_at = datetime.now(UTC)

    async def revoke_by_refresh_hash(self, refresh_token_hash):
        session = self.sessions.get(refresh_token_hash)
        if session:
            session.revoked_at = datetime.now(UTC)

    async def update_last_login(self, user_id):
        logged_in_at = datetime.now(UTC)
        user = await self.get_user_by_id(user_id)
        user.last_login_at = logged_in_at
        return logged_in_at

    async def update_password(self, user_id, password_hash):
        user = await self.get_user_by_id(user_id)
        user.password_hash = password_hash

    async def revoke_user_sessions(self, user_id):
        for session in self.sessions.values():
            if session.user_id == user_id:
                session.revoked_at = datetime.now(UTC)


class FakeCodeStore:
    """In-memory email-code store."""

    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def create_register_code(self, email: str) -> str:
        self.codes[f"register:{email}"] = "123456"
        return "123456"

    async def create_password_reset_code(self, email: str) -> str:
        self.codes[f"password_reset:{email}"] = "654321"
        return "654321"

    async def verify_register_code(self, email: str, code: str) -> None:
        if self.codes.get(f"register:{email}") != code:
            raise ValueError("bad code")

    async def verify_password_reset_code(self, email: str, code: str) -> None:
        if self.codes.get(f"password_reset:{email}") != code:
            raise ValueError("bad code")

    async def delete_register_code(self, email: str) -> None:
        self.codes.pop(f"register:{email}", None)

    async def delete_password_reset_code(self, email: str) -> None:
        self.codes.pop(f"password_reset:{email}", None)


class FakeMailSender:
    """Capture outgoing verification-code emails."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def ensure_configured(self) -> None:
        return None

    async def send_register_code(self, *, email: str, code: str) -> None:
        self.sent.append((email, code))

    async def send_password_reset_code(self, *, email: str, code: str) -> None:
        self.sent.append((email, code))


def test_register_hashes_password_and_sets_cookies() -> None:
    """Registering creates a verified user, hashes password, and writes cookies."""
    asyncio.run(_register_hashes_password_and_sets_cookies())


async def _register_hashes_password_and_sets_cookies() -> None:
    repository = FakeRepository()
    code_store = FakeCodeStore()
    service = AuthService(
        repository=repository,
        code_store=code_store,
        mail_sender=FakeMailSender(),
        settings=_settings(),
    )
    await service.send_register_code("PLAYER@EXAMPLE.COM")

    response = Response()
    result = await service.register(
        email="PLAYER@EXAMPLE.COM",
        password="correct horse battery staple",
        code="123456",
        display_name="Player",
        response=response,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )

    user = repository.users["player@example.com"]
    assert result.user.email == "player@example.com"
    assert user.password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", user.password_hash)
    set_cookie_headers = [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]
    assert any(ACCESS_COOKIE_NAME in header for header in set_cookie_headers)
    assert any(REFRESH_COOKIE_NAME in header for header in set_cookie_headers)


def test_login_rejects_wrong_password() -> None:
    """Wrong passwords do not issue cookies."""
    asyncio.run(_login_rejects_wrong_password())


async def _login_rejects_wrong_password() -> None:
    repository = FakeRepository()
    code_store = FakeCodeStore()
    service = AuthService(
        repository=repository,
        code_store=code_store,
        mail_sender=FakeMailSender(),
        settings=_settings(),
    )
    await service.send_register_code("player@example.com")
    await service.register(
        email="player@example.com",
        password="correct horse battery staple",
        code="123456",
        display_name=None,
        response=Response(),
        user_agent=None,
        ip_address=None,
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            email="player@example.com",
            password="wrong",
            response=Response(),
            user_agent=None,
            ip_address=None,
        )


def test_password_reset_updates_hash_and_revokes_sessions() -> None:
    """Password reset updates stored hash and revokes existing refresh sessions."""
    asyncio.run(_password_reset_updates_hash_and_revokes_sessions())


async def _password_reset_updates_hash_and_revokes_sessions() -> None:
    repository = FakeRepository()
    code_store = FakeCodeStore()
    service = AuthService(
        repository=repository,
        code_store=code_store,
        mail_sender=FakeMailSender(),
        settings=_settings(),
    )
    await service.send_register_code("player@example.com")
    await service.register(
        email="player@example.com",
        password="old password 123",
        code="123456",
        display_name=None,
        response=Response(),
        user_agent=None,
        ip_address=None,
    )
    assert any(session.revoked_at is None for session in repository.sessions.values())

    await service.send_password_reset_code("player@example.com")
    await service.reset_password(
        email="player@example.com",
        code="654321",
        new_password="new password 456",
    )

    user = repository.users["player@example.com"]
    assert not verify_password("old password 123", user.password_hash)
    assert verify_password("new password 456", user.password_hash)
    assert all(session.revoked_at is not None for session in repository.sessions.values())


def _settings() -> Settings:
    return Settings(
        AUTH_SECRET_KEY="test-secret-key-with-at-least-thirty-two-bytes",
        AUTH_ACCESS_TOKEN_MINUTES=30,
        AUTH_REFRESH_TOKEN_DAYS=30,
    )
