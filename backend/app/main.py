"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.games import router as games_router
from app.api.health import router as health_router
from app.api.llm_config import router as llm_config_router
from app.api.websocket import router as websocket_router
from app.auth.router import router as auth_router
from app.cache.redis_client import close_redis
from app.config import get_settings
from app.db.session import close_db, init_db
from app.sessions.manager import manager


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """管理应用生命周期，关闭时释放内存会话和 WebSocket 资源。"""
        try:
            await init_db()
        except SQLAlchemyError:
            pass
        yield
        await close_redis()
        await close_db()
        await manager.close()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # 允许访问后端的前端来源
        allow_credentials=True,  # 允许浏览器携带 Cookie 或认证信息
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有请求头
    )

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(llm_config_router, prefix=settings.api_prefix)
    app.include_router(games_router, prefix=settings.api_prefix)
    app.include_router(websocket_router)
    return app


app = create_app()
