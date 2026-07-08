"""从环境变量读取的应用配置。"""

import csv
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """后端运行时配置。"""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WolfArena AI"  # 应用名称
    app_version: str = "0.1.0"  # 应用版本
    app_env: Literal["local", "development", "staging", "production"] = "local"  # 运行环境
    api_prefix: str = "/api"  # REST API 前缀
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
    )

    llm_provider: str = "openai_compatible"  # LLM provider 类型
    llm_base_url: str = Field(
        default="https://api.example.com/v1",
        validation_alias="LLM_BASE_URL",
    )
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", validation_alias="LLM_MODEL")
    llm_timeout_seconds: int = Field(default=60, validation_alias="LLM_TIMEOUT_SECONDS")

    database_url: str = Field(
        default="postgresql+asyncpg://wolf_user:wolf_password@postgres:5432/wolf_game",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", validation_alias="REDIS_URL")

    auth_secret_key: str = Field(default="change-me", validation_alias="AUTH_SECRET_KEY")
    auth_access_token_minutes: int = Field(default=30, validation_alias="AUTH_ACCESS_TOKEN_MINUTES")
    auth_refresh_token_days: int = Field(default=30, validation_alias="AUTH_REFRESH_TOKEN_DAYS")
    auth_cookie_secure: bool = Field(default=False, validation_alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        validation_alias="AUTH_COOKIE_SAMESITE",
    )

    email_code_ttl_seconds: int = Field(default=300, validation_alias="EMAIL_CODE_TTL_SECONDS")
    email_code_cooldown_seconds: int = Field(
        default=60,
        validation_alias="EMAIL_CODE_COOLDOWN_SECONDS",
    )
    email_code_daily_limit: int = Field(default=10, validation_alias="EMAIL_CODE_DAILY_LIMIT")
    email_code_fail_limit: int = Field(default=5, validation_alias="EMAIL_CODE_FAIL_LIMIT")
    email_code_fail_ttl_seconds: int = Field(
        default=900,
        validation_alias="EMAIL_CODE_FAIL_TTL_SECONDS",
    )

    aliyun_mail_access_key_id: str = Field(
        default="",
        validation_alias="ALIYUN_MAIL_ACCESS_KEY_ID",
    )
    aliyun_mail_access_key_secret: str = Field(
        default="",
        validation_alias="ALIYUN_MAIL_ACCESS_KEY_SECRET",
    )
    aliyun_mail_account_name: str = Field(
        default="",
        validation_alias="ALIYUN_MAIL_ACCOUNT_NAME",
    )
    aliyun_mail_from_alias: str = Field(
        default="WolfArena AI",
        validation_alias="ALIYUN_MAIL_FROM_ALIAS",
    )
    aliyun_mail_endpoint: str = Field(
        default="https://dm.aliyuncs.com/",
        validation_alias="ALIYUN_MAIL_ENDPOINT",
    )

    @property
    def resolved_aliyun_mail_access_key_id(self) -> str:
        """Return Aliyun AccessKey ID from env or local AccessKey.csv."""
        if self.aliyun_mail_access_key_id.strip():
            return self.aliyun_mail_access_key_id.strip()
        return _read_access_key_csv().get("access_key_id", "")

    @property
    def resolved_aliyun_mail_access_key_secret(self) -> str:
        """Return Aliyun AccessKey Secret from env or local AccessKey.csv."""
        if self.aliyun_mail_access_key_secret.strip():
            return self.aliyun_mail_access_key_secret.strip()
        return _read_access_key_csv().get("access_key_secret", "")

    @property
    def resolved_aliyun_mail_account_name(self) -> str:
        """Return Aliyun sender account from env or local AccessKey.csv if present."""
        if self.aliyun_mail_account_name.strip():
            return self.aliyun_mail_account_name.strip()
        return _read_access_key_csv().get("account_name", "")

    @computed_field  # type: ignore[misc]
    @property
    def cors_origins(self) -> list[str]:
        """返回规范化后的 CORS 来源列表。"""
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]

    @property
    def llm_api_key_configured(self) -> bool:
        """返回是否已经配置 LLM API key。"""
        return bool(self.llm_api_key.strip())

    @property
    def masked_llm_api_key(self) -> str:
        """返回用于诊断展示的脱敏 API key。"""
        key = self.llm_api_key.strip()
        if not key:
            return ""
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


@lru_cache
def get_settings() -> Settings:
    """返回带缓存的应用配置对象。"""
    return Settings()


@lru_cache
def _read_access_key_csv() -> dict[str, str]:
    """Read local Aliyun credentials without exposing them in source or env files."""
    path = PROJECT_ROOT / "AccessKey.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        row = next(csv.DictReader(file), None)
    if row is None:
        return {}
    return {
        "access_key_id": _first_present(row, "AccessKey ID", "ALIYUN_MAIL_ACCESS_KEY_ID"),
        "access_key_secret": _first_present(
            row,
            "AccessKey Secret",
            "ALIYUN_MAIL_ACCESS_KEY_SECRET",
        ),
        "account_name": _first_present(
            row,
            "AccountName",
            "Account Name",
            "ALIYUN_MAIL_ACCOUNT_NAME",
        ),
    }


def _first_present(row: dict[str, str], *keys: str) -> str:
    """Return the first non-empty CSV value for any accepted header."""
    for key in keys:
        value = row.get(key)
        if value and value.strip():
            return value.strip()
    return ""
