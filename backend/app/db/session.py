"""Database engine and async session helpers."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    async with AsyncSessionLocal() as session:
        yield session        # ← 这里暂停，把 session 交出去
        # ← 路由函数 return 后，代码继续执行到这里
        #   __aexit__ 自动关闭 session


async def init_db() -> None:
    """Create application tables when migrations have not been run yet."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose database connections."""
    await engine.dispose()
