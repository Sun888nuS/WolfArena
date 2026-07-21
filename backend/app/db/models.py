"""SQLAlchemy models for persistent application data."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
# SQLAlchemy 是 Python 中最常用的数据库工具库之一。它负责让 Python 代码连接、查询和更新关系型数据库，例如 PostgreSQL、MySQL、SQLite 等。
# 它提供了一种基于类的 API 来定义数据库表结构，以及通过映射关系来处理数据库中的数据。
# 这使得开发人员可以更方便地编写数据库操作代码，而不需要直接使用 SQL 语句。
# 它还支持异步数据库操作，以及与 ORM 框架（如 SQLAlchemy ORM）的集成。
# ORM：用 Python 类描述数据库表。例如 User 类对应 users 表，类属性 email 对应表中的 email 列。
# 代码操作对象，SQLAlchemy 负责生成 SQL 语句。
# SQLAlchemy 是后端 Python 代码与 PostgreSQL 之间的访问层，负责处理数据库操作。

class Base(DeclarativeBase):
    """Shared declarative base for ORM models."""


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class User(Base):
    """Registered user account.
    保存用户 ID、邮箱、密码哈希、昵称、启用状态、邮箱验证状态、创建/更新时间与最近登录时间
    """

    __tablename__ = "users"
    # 用户表结构
    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    #一个用户可拥有多个会话；删除用户时，其所有会话会由数据库级联删除


class UserSession(Base):
    """Refresh-token-backed browser session.
    保存用户会话 ID、用户 ID、刷新令牌哈希、用户代理、IP 地址、过期时间、撤销时间、创建时间
    """

    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="sessions")
