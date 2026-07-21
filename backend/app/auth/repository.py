"""Database access helpers for auth."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserSession, utc_now

# 查询、创建用户、创建、查询、撤销刷新令牌会话、更新密码和最后登录时间、通过 revoked_at 标记会话失效，而不是立即删除记录
class AuthRepository:
    """Repository for users and refresh-token sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_email(self, email: str) -> User | None:
        """Return a user by normalized email."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Return an active user by id."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none() # 取第一条结果，没有则返回 None（不会抛异常）

    async def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str | None,
        email_verified: bool,
    ) -> User:
        """Create and flush a new user."""
        user = User(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            email_verified=email_verified,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def create_session(
        self,
        *,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> UserSession:
        """Persist a refresh-token session."""
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get_active_session_by_refresh_hash(
        self,
        refresh_token_hash: str,
        *,
        now: datetime,
    ) -> UserSession | None:
        """Return a non-revoked, non-expired refresh session."""
        result = await self.session.execute(
            select(UserSession)
            .where(UserSession.refresh_token_hash == refresh_token_hash)
            .where(UserSession.revoked_at.is_(None))
            .where(UserSession.expires_at > now),
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, session_id: UUID) -> None:
        """Mark one refresh-token session revoked."""
        await self.session.execute(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(revoked_at=utc_now()),
        )

    async def revoke_by_refresh_hash(self, refresh_token_hash: str) -> None:
        """Mark a refresh-token session revoked by token hash."""
        await self.session.execute(
            update(UserSession)
            .where(UserSession.refresh_token_hash == refresh_token_hash)
            .where(UserSession.revoked_at.is_(None))
            .values(revoked_at=utc_now()),
        )

    async def update_last_login(self, user_id: UUID) -> datetime:
        """Update the user's last login timestamp."""
        logged_in_at = utc_now()
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=logged_in_at, updated_at=logged_in_at),
        )
        return logged_in_at

    async def update_password(self, user_id: UUID, password_hash: str) -> None:
        """Update a user's password hash."""
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash, updated_at=utc_now()),
        )

    async def revoke_user_sessions(self, user_id: UUID) -> None:
        """Revoke all active refresh-token sessions for a user."""
        await self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .values(revoked_at=utc_now()),
        )
