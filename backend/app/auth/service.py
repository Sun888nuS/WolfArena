"""Application service for registration and login flows."""

from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy.exc import IntegrityError

from app.auth.email_sender import AliyunMailSender
from app.auth.exceptions import (
    AuthError,
    DuplicateEmailError,
    InactiveUserError,
    InvalidCredentialsError,
)
from app.auth.redis_codes import RedisEmailCodeStore
from app.auth.repository import AuthRepository
from app.auth.schemas import AuthResponse, UserResponse
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    set_auth_cookies,
    verify_password,
)
from app.config import Settings
from app.db.models import User


class AuthService:
    """Coordinate auth repositories, Redis code storage, mail, and cookies."""

    def __init__(
        self,
        *,
        repository: AuthRepository,
        code_store: RedisEmailCodeStore,
        mail_sender: AliyunMailSender,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.code_store = code_store
        self.mail_sender = mail_sender
        self.settings = settings

    async def send_register_code(self, email: str) -> None:
        """Generate and email a registration code."""
        normalized_email = normalize_email(email)
        if await self.repository.get_user_by_email(normalized_email):
            raise DuplicateEmailError()
        self.mail_sender.ensure_configured()
        code = await self.code_store.create_register_code(normalized_email)
        try:
            await self.mail_sender.send_register_code(email=normalized_email, code=code)
        except Exception:
            await self.code_store.delete_register_code(normalized_email)
            raise

    async def send_password_reset_code(self, email: str) -> None:
        """Generate and email a password reset code."""
        normalized_email = normalize_email(email)
        user = await self.repository.get_user_by_email(normalized_email)
        if user is None:
            raise AuthError("邮箱未注册", status_code=404)
        if not user.is_active:
            raise InactiveUserError()
        self.mail_sender.ensure_configured()
        code = await self.code_store.create_password_reset_code(normalized_email)
        try:
            await self.mail_sender.send_password_reset_code(email=normalized_email, code=code)
        except Exception:
            await self.code_store.delete_password_reset_code(normalized_email)
            raise

    async def register(
        self,
        *,
        email: str,
        password: str,
        code: str,
        display_name: str | None,
        response: Response,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResponse:
        """Register a new account and log it in immediately."""
        normalized_email = normalize_email(email)
        if await self.repository.get_user_by_email(normalized_email):
            raise DuplicateEmailError()
        await self.code_store.verify_register_code(normalized_email, code)
        try:
            user = await self.repository.create_user(
                email=normalized_email,
                password_hash=hash_password(password),
                display_name=normalize_display_name(display_name),
                email_verified=True,
            )
            result = await self._issue_tokens(
                user=user,
                response=response,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        except IntegrityError as exc:
            raise DuplicateEmailError() from exc
        await self.code_store.delete_register_code(normalized_email)
        return result

    async def login(
        self,
        *,
        email: str,
        password: str,
        response: Response,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResponse:
        """Authenticate a user and issue cookies."""
        user = await self.repository.get_user_by_email(normalize_email(email))
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()
        return await self._issue_tokens(
            user=user,
            response=response,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    async def reset_password(
        self,
        *,
        email: str,
        code: str,
        new_password: str,
    ) -> None:
        """Reset password using an email verification code."""
        normalized_email = normalize_email(email)
        user = await self.repository.get_user_by_email(normalized_email)
        if user is None:
            raise AuthError("邮箱未注册", status_code=404)
        if not user.is_active:
            raise InactiveUserError()
        await self.code_store.verify_password_reset_code(normalized_email, code)
        await self.repository.update_password(user.id, hash_password(new_password))
        await self.repository.revoke_user_sessions(user.id)
        await self.code_store.delete_password_reset_code(normalized_email)

    async def refresh(
        self,
        *,
        refresh_token: str | None,
        response: Response,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResponse:
        """Rotate a valid refresh token and issue fresh cookies."""
        if not refresh_token:
            raise AuthError("未登录", status_code=401)
        now = datetime.now(UTC)
        refresh_hash = hash_token(refresh_token)
        session = await self.repository.get_active_session_by_refresh_hash(refresh_hash, now=now)
        if session is None:
            raise AuthError("登录状态已过期", status_code=401)
        user = await self.repository.get_user_by_id(session.user_id)
        if user is None or not user.is_active:
            raise AuthError("登录状态无效", status_code=401)
        await self.repository.revoke_session(session.id)
        return await self._issue_tokens(
            user=user,
            response=response,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke the current refresh token when present."""
        if refresh_token:
            await self.repository.revoke_by_refresh_hash(hash_token(refresh_token))

    async def _issue_tokens(
        self,
        *,
        user: User,
        response: Response,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResponse:
        access_token = create_access_token(user.id, self.settings)
        refresh_token = create_refresh_token()
        await self.repository.create_session(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=self.settings.auth_refresh_token_days),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        user.last_login_at = await self.repository.update_last_login(user.id)
        set_auth_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            settings=self.settings,
        )
        return AuthResponse(user=user_to_response(user))


def normalize_email(email: str) -> str:
    """Normalize email for account identity."""
    return email.strip().lower()


def normalize_display_name(display_name: str | None) -> str | None:
    """Trim optional display names."""
    if display_name is None:
        return None
    value = display_name.strip()
    return value or None


def user_to_response(user: User) -> UserResponse:
    """Convert a user ORM model to a safe response."""
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified=user.email_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
