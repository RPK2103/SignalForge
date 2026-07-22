from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ENV_FILE

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
AppEnv = Literal["development", "staging", "production"]

DEFAULT_DEV_CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://127.0.0.1:3000,"
    "http://localhost:8000,"
    "http://127.0.0.1:8000"
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

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in DEFAULT_DEV_CORS_ORIGINS.split(",")
            if origin.strip()
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return [
                origin.strip()
                for origin in DEFAULT_DEV_CORS_ORIGINS.split(",")
                if origin.strip()
            ]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "*":
                return ["*"]
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
