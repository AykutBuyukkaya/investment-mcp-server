from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    transport: Literal["stdio", "sse", "streamable-http"] = Field(
        default="stdio",
        validation_alias=AliasChoices("MCP_TRANSPORT", "transport"),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("MCP_LOG_LEVEL", "INVESTMENT_MCP_LOG_LEVEL", "log_level"),
    )
    yf_base_url: str = Field(
        default="https://query2.finance.yahoo.com",
        validation_alias=AliasChoices("YF_BASE_URL", "MCP_YF_BASE_URL", "yf_base_url"),
    )
    yf_timeout_connect_seconds: float = Field(
        default=3.0,
        gt=0,
        validation_alias=AliasChoices(
            "YF_TIMEOUT_CONNECT_SECONDS",
            "MCP_YF_TIMEOUT_CONNECT_SECONDS",
            "yf_timeout_connect_seconds",
        ),
    )
    yf_timeout_read_seconds: float = Field(
        default=7.0,
        gt=0,
        validation_alias=AliasChoices(
            "YF_TIMEOUT_READ_SECONDS",
            "MCP_YF_TIMEOUT_READ_SECONDS",
            "yf_timeout_read_seconds",
        ),
    )
    yf_timeout_total_seconds: float = Field(
        default=10.0,
        gt=0,
        validation_alias=AliasChoices(
            "YF_TIMEOUT_TOTAL_SECONDS",
            "MCP_YF_TIMEOUT_TOTAL_SECONDS",
            "yf_timeout_total_seconds",
        ),
    )
    yf_max_retries: int = Field(
        default=3,
        ge=0,
        validation_alias=AliasChoices("YF_MAX_RETRIES", "MCP_YF_MAX_RETRIES", "yf_max_retries"),
    )
    yf_retry_backoff_base: float = Field(
        default=0.25,
        gt=0,
        validation_alias=AliasChoices(
            "YF_RETRY_BACKOFF_BASE",
            "MCP_YF_RETRY_BACKOFF_BASE",
            "yf_retry_backoff_base",
        ),
    )
    yf_user_agent: str = Field(
        default="investment-mcp-server/0.1.0",
        validation_alias=AliasChoices("YF_USER_AGENT", "MCP_YF_USER_AGENT", "yf_user_agent"),
    )
    yf_default_include_prepost: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "YF_DEFAULT_INCLUDE_PREPOST",
            "MCP_YF_DEFAULT_INCLUDE_PREPOST",
            "yf_default_include_prepost",
        ),
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            options = ", ".join(sorted(allowed))
            raise ValueError(f"log_level must be one of: {options}")
        return normalized

    @field_validator("yf_base_url")
    @classmethod
    def validate_yf_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not (normalized.startswith("https://") or normalized.startswith("http://")):
            raise ValueError("yf_base_url must start with http:// or https://")
        return normalized

    @field_validator("yf_user_agent")
    @classmethod
    def validate_yf_user_agent(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("yf_user_agent cannot be empty")
        return value.strip()
