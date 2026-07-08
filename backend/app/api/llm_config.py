"""Runtime LLM configuration API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings

router = APIRouter(prefix="/llm", tags=["llm"])


class LlmConfigResponse(BaseModel):
    """Safe runtime LLM configuration returned to the frontend."""

    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    api_key_preview: str
    timeout_seconds: int
    status: str


class UpdateLlmConfigRequest(BaseModel):
    """Runtime LLM configuration update request."""

    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = Field(default=None, max_length=4000)


@router.get("/config", response_model=LlmConfigResponse)
def get_llm_config() -> LlmConfigResponse:
    """Return the current runtime LLM configuration without exposing the raw key."""
    return _response_from_settings()


@router.put("/config", response_model=LlmConfigResponse)
def update_llm_config(request: UpdateLlmConfigRequest) -> LlmConfigResponse:
    """Update the runtime LLM configuration used by subsequent Agent calls."""
    base_url = request.base_url.strip().rstrip("/")
    model = request.model.strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="API URL 不能为空")
    if not model:
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    settings = get_settings()
    settings.llm_base_url = base_url
    settings.llm_model = model
    if request.api_key is not None and request.api_key.strip():
        settings.llm_api_key = request.api_key.strip()
    return _response_from_settings()


def _response_from_settings() -> LlmConfigResponse:
    settings = get_settings()
    return LlmConfigResponse(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key_configured=settings.llm_api_key_configured,
        api_key_preview=settings.masked_llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        status="online multi-agent" if settings.llm_api_key_configured else "online agent not configured",
    )
