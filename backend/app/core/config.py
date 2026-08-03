import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.paths import ENV_FILE

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
AppEnv = Literal["development", "staging", "production"]
LogFormat = Literal["text", "json"]
OtelExporterMode = Literal["none", "console", "otlp"]

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

    # ------------------------------------------------------------------
    # Observability & AI quality (Phase 3 Prompt 8).
    #
    # Defaults are safe for local/test: telemetry is enabled (recording to the
    # in-memory/no-op providers) but no network exporter runs. Production may
    # opt into OTLP export via OTEL_EXPORTER_MODE=otlp with a validated endpoint.
    # No raw exporter credentials are ever stored here; headers are resolved via
    # an approved secret-reference boundary (never printed in snapshots).
    # ------------------------------------------------------------------
    observability_enabled: bool = Field(default=True, validation_alias="OBSERVABILITY_ENABLED")
    log_format: LogFormat = Field(default="text", validation_alias="LOG_FORMAT")
    otel_service_name: str = Field(default="signalforge-api", validation_alias="OTEL_SERVICE_NAME")
    otel_service_version: str = Field(default="0.0.0", validation_alias="OTEL_SERVICE_VERSION")
    otel_exporter_mode: OtelExporterMode = Field(
        default="none", validation_alias="OTEL_EXPORTER_MODE"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    # A reference (env-var name / secret store key) — NOT the raw header value.
    otel_exporter_otlp_headers_secret_ref: str = Field(
        default="", validation_alias="OTEL_EXPORTER_OTLP_HEADERS_SECRET_REF"
    )
    otel_export_timeout_seconds: int = Field(
        default=10, validation_alias="OTEL_EXPORT_TIMEOUT_SECONDS"
    )
    otel_batch_max_queue_size: int = Field(
        default=2048, validation_alias="OTEL_BATCH_MAX_QUEUE_SIZE"
    )
    otel_batch_max_export_size: int = Field(
        default=512, validation_alias="OTEL_BATCH_MAX_EXPORT_SIZE"
    )
    otel_trace_sample_ratio: float = Field(default=1.0, validation_alias="OTEL_TRACE_SAMPLE_RATIO")
    metric_rollup_interval_seconds: int = Field(
        default=60, validation_alias="METRIC_ROLLUP_INTERVAL_SECONDS"
    )
    metric_retention_days: int = Field(default=30, validation_alias="METRIC_RETENTION_DAYS")
    ai_eval_enabled: bool = Field(default=True, validation_alias="AI_EVAL_ENABLED")
    ai_eval_release_gate_enabled: bool = Field(
        default=True, validation_alias="AI_EVAL_RELEASE_GATE_ENABLED"
    )
    alert_evaluation_enabled: bool = Field(
        default=True, validation_alias="ALERT_EVALUATION_ENABLED"
    )

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

    @field_validator("otel_trace_sample_ratio")
    @classmethod
    def validate_sample_ratio(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("OTEL_TRACE_SAMPLE_RATIO must be between 0.0 and 1.0")
        return value

    @field_validator("otel_export_timeout_seconds")
    @classmethod
    def validate_export_timeout(cls, value: int) -> int:
        if value < 1 or value > 120:
            raise ValueError("OTEL_EXPORT_TIMEOUT_SECONDS must be between 1 and 120")
        return value

    @field_validator("otel_batch_max_queue_size")
    @classmethod
    def validate_queue_size(cls, value: int) -> int:
        if value < 1 or value > 65536:
            raise ValueError("OTEL_BATCH_MAX_QUEUE_SIZE must be between 1 and 65536")
        return value

    @field_validator("otel_batch_max_export_size")
    @classmethod
    def validate_export_size(cls, value: int) -> int:
        if value < 1 or value > 8192:
            raise ValueError("OTEL_BATCH_MAX_EXPORT_SIZE must be between 1 and 8192")
        return value

    @field_validator("metric_rollup_interval_seconds")
    @classmethod
    def validate_rollup_interval(cls, value: int) -> int:
        if value < 5 or value > 3600:
            raise ValueError("METRIC_ROLLUP_INTERVAL_SECONDS must be between 5 and 3600")
        return value

    @field_validator("metric_retention_days")
    @classmethod
    def validate_retention_days(cls, value: int) -> int:
        if value < 1 or value > 365:
            raise ValueError("METRIC_RETENTION_DAYS must be between 1 and 365")
        return value

    @field_validator("otel_exporter_otlp_endpoint")
    @classmethod
    def validate_otlp_endpoint(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            return ""
        if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be an http(s) URL when set")
        return trimmed

    @model_validator(mode="after")
    def validate_exporter_requirements(self) -> "Settings":
        # Only fail startup for configuration required by the SELECTED exporter
        # mode. The OTLP exporter requires a validated endpoint; console/none do
        # not require any network configuration.
        if self.otel_exporter_mode == "otlp" and not self.otel_exporter_otlp_endpoint:
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT is required when OTEL_EXPORTER_MODE=otlp")
        return self

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
            "observability_enabled": self.observability_enabled,
            "log_format": self.log_format,
            "otel_service_name": self.otel_service_name,
            "otel_exporter_mode": self.otel_exporter_mode,
            "otel_exporter_endpoint_set": bool(self.otel_exporter_otlp_endpoint.strip()),
            # Never expose the resolved header value; only whether a ref is set.
            "otel_exporter_headers_ref_set": bool(
                self.otel_exporter_otlp_headers_secret_ref.strip()
            ),
            "ai_eval_enabled": self.ai_eval_enabled,
            "ai_eval_release_gate_enabled": self.ai_eval_release_gate_enabled,
            "alert_evaluation_enabled": self.alert_evaluation_enabled,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
