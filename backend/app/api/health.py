"""健康检查和安全配置诊断接口。"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["health"])


class LlmConfigStatus(BaseModel):
    """可安全返回给前端的大模型配置状态。"""

    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    api_key_preview: str
    timeout_seconds: int


class HealthResponse(BaseModel):
    """健康检查响应体。"""

    status: str
    app_name: str
    app_version: str
    app_env: str
    checked_at: datetime
    llm: LlmConfigStatus


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """返回服务健康状态和脱敏后的大模型配置。"""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_version=settings.app_version,
        app_env=settings.app_env,
        checked_at=datetime.now(UTC),
        llm=LlmConfigStatus(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key_configured=settings.llm_api_key_configured,
            api_key_preview=settings.masked_llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
    )
