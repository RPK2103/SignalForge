import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.paths import ENV_FILE

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
AppEnv = Literal["development", "staging", "production"]

DEFAULT_DEV_CORS_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnv = Field(default="development", validation_alias="APP_ENV")
    log_level: LogLevel = Field(default="INFO", validation_alias="LOG_LEVEL")
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")

    # NoDecode: keep pydantic-settings from JSON-decoding this list field so the
    # validator below can accept comma-separated, JSON-array, "*" or plain values.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            origin.strip() for origin in DEFAULT_DEV_CORS_ORIGINS.split(",") if origin.strip()
        ],
        validation_alias="CORS_ORIGINS",
    )

    azure_openai_endpoint: str = Field(default="", validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = Field(default="", validation_alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(
        default="2024-10-21",
        validation_alias="AZURE_OPENAI_API_VERSION",
    )
    ai_enabled: bool = Field(default=True, validation_alias="AI_ENABLED")
    ai_request_timeout_seconds: int = Field(
        default=30,
        validation_alias="AI_REQUEST_TIMEOUT_SECONDS",
    )
    ai_max_retries: int = Field(default=2, validation_alias="AI_MAX_RETRIES")

    @field_validator("ai_request_timeout_seconds")
    @classmethod
    def validate_ai_timeout(cls, value: int) -> int:
        if value < 1 or value > 120:
            raise ValueError("AI_REQUEST_TIMEOUT_SECONDS must be between 1 and 120")
        return value

    @field_validator("ai_max_retries")
    @classmethod
    def validate_ai_retries(cls, value: int) -> int:
        if value < 0 or value > 5:
            raise ValueError("AI_MAX_RETRIES must be between 0 and 5")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return [
                origin.strip() for origin in DEFAULT_DEV_CORS_ORIGINS.split(",") if origin.strip()
            ]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "*":
                return ["*"]
            # Accept a JSON array string (e.g. from a Render/Vercel env var).
            if trimmed.startswith("["):
                try:
                    parsed = json.loads(trimmed)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(origin).strip() for origin in parsed if str(origin).strip()]
            # Otherwise treat as a comma-separated or single plain origin.
            return [origin.strip() for origin in trimmed.split(",") if origin.strip()]
        raise TypeError("CORS_ORIGINS must be a comma-separated string or list")

    def azure_openai_configured(self) -> bool:
        if not self.ai_enabled:
            return False
        return bool(
            self.azure_openai_endpoint.strip()
            and self.azure_openai_api_key.strip()
            and self.azure_openai_deployment.strip()
        )

    def startup_snapshot(self) -> dict[str, object]:
        """Safe settings summary for logs (no secrets)."""
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "database_configured": bool(self.database_url),
            "cors_origins": self.cors_origins,
            "ai_enabled": self.ai_enabled,
            "azure_openai_configured": self.azure_openai_configured(),
            "azure_openai_api_version": self.azure_openai_api_version,
            "azure_openai_deployment_set": bool(self.azure_openai_deployment.strip()),
            "azure_openai_endpoint_set": bool(self.azure_openai_endpoint.strip()),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
