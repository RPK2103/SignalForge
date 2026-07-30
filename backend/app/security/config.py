"""Security configuration with fail-closed production validation (Prompt 7).

Production MUST use Entra OIDC and MUST fail startup when authentication is
disabled or incompletely configured. ``local_development`` and ``test`` modes are
impossible in production. No secret has a hardcoded default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.config import AppEnv, get_settings
from app.core.paths import ENV_FILE
from app.security.enums import AuthenticationMode
from app.security.exceptions import SecurityConfigError

# Entra production tokens are RS256 by default; an explicit allowlist prevents
# algorithm-confusion and "alg: none" attacks.
_ENTRA_ALLOWED_ALGORITHMS = ("RS256", "RS384", "RS512")
_LOCAL_DEV_ALGORITHM = "HS256"
MIN_LOCAL_AUTH_SECRET_LENGTH = 32
MAX_TOKEN_BYTES = 8192


def _split_csv(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [item.strip() for item in text.split(",") if item.strip()]


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    auth_mode: AuthenticationMode = Field(
        default=AuthenticationMode.LOCAL_DEVELOPMENT,
        validation_alias="AUTH_MODE",
    )

    # -- Entra OIDC ---------------------------------------------------------
    entra_issuer: str = Field(default="", validation_alias="ENTRA_ISSUER")
    entra_audience: str = Field(default="", validation_alias="ENTRA_AUDIENCE")
    entra_jwks_uri: str = Field(default="", validation_alias="ENTRA_JWKS_URI")
    entra_allowed_tenant_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="ENTRA_ALLOWED_TENANT_IDS",
    )
    jwt_clock_skew_seconds: int = Field(default=60, validation_alias="JWT_CLOCK_SKEW_SECONDS")

    # -- JWKS caching -------------------------------------------------------
    jwks_cache_ttl_seconds: int = Field(default=600, validation_alias="JWKS_CACHE_TTL_SECONDS")
    jwks_request_timeout_seconds: float = Field(
        default=5.0, validation_alias="JWKS_REQUEST_TIMEOUT_SECONDS"
    )
    jwks_max_response_bytes: int = Field(
        default=1_048_576, validation_alias="JWKS_MAX_RESPONSE_BYTES"
    )

    # -- Local development token signing -----------------------------------
    # Secret MUST come from a protected env var; there is no default.
    local_auth_secret: str = Field(default="", validation_alias="SIGNALFORGE_LOCAL_AUTH_SECRET")
    local_dev_token_ttl_seconds: int = Field(
        default=3600, validation_alias="LOCAL_DEV_TOKEN_TTL_SECONDS"
    )
    local_dev_issuer: str = Field(
        default="signalforge-local-dev", validation_alias="LOCAL_DEV_ISSUER"
    )
    local_dev_audience: str = Field(
        default="signalforge-api", validation_alias="LOCAL_DEV_AUDIENCE"
    )

    # -- HTTP hardening -----------------------------------------------------
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"],
        validation_alias="TRUSTED_HOSTS",
    )
    docs_enabled: bool = Field(default=True, validation_alias="DOCS_ENABLED")
    hsts_enabled: bool = Field(default=False, validation_alias="HSTS_ENABLED")

    # -- Database role assumptions (documented, validated) ------------------
    db_application_role: str = Field(
        default="signalforge_app", validation_alias="DB_APPLICATION_ROLE"
    )
    db_migration_role: str = Field(
        default="signalforge_migrator", validation_alias="DB_MIGRATION_ROLE"
    )

    @field_validator("entra_allowed_tenant_ids", "trusted_hosts", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> list[str]:
        return _split_csv(value)

    @field_validator("jwt_clock_skew_seconds")
    @classmethod
    def _validate_skew(cls, value: int) -> int:
        if value < 0 or value > 300:
            raise ValueError("JWT_CLOCK_SKEW_SECONDS must be between 0 and 300")
        return value

    @field_validator("local_dev_token_ttl_seconds")
    @classmethod
    def _validate_dev_ttl(cls, value: int) -> int:
        if value < 60 or value > 86_400:
            raise ValueError("LOCAL_DEV_TOKEN_TTL_SECONDS must be between 60 and 86400")
        return value

    # -- Derived helpers ----------------------------------------------------
    @property
    def entra_allowed_algorithms(self) -> tuple[str, ...]:
        return _ENTRA_ALLOWED_ALGORITHMS

    @property
    def local_dev_algorithm(self) -> str:
        return _LOCAL_DEV_ALGORITHM

    @property
    def max_token_bytes(self) -> int:
        return MAX_TOKEN_BYTES

    def local_auth_secret_is_strong(self) -> bool:
        return len(self.local_auth_secret) >= MIN_LOCAL_AUTH_SECRET_LENGTH

    def safe_snapshot(self) -> dict[str, object]:
        """Secret-free summary for startup logs."""
        return {
            "auth_mode": self.auth_mode.value,
            "entra_issuer_set": bool(self.entra_issuer.strip()),
            "entra_audience_set": bool(self.entra_audience.strip()),
            "entra_jwks_uri_set": bool(self.entra_jwks_uri.strip()),
            "entra_allowed_tenants": len(self.entra_allowed_tenant_ids),
            "docs_enabled": self.docs_enabled,
            "hsts_enabled": self.hsts_enabled,
            "trusted_hosts": self.trusted_hosts,
            "local_auth_secret_set": bool(self.local_auth_secret),
        }

    def validate_for_environment(self, app_env: AppEnv, cors_origins: list[str]) -> None:
        """Fail closed on unsafe configuration.

        Raises :class:`SecurityConfigError` (fatal at startup) when production
        authentication is disabled or misconfigured.
        """
        errors: list[str] = []

        # CORS: never allow wildcard origin with credentials, in any environment.
        if "*" in cors_origins:
            errors.append(
                "Wildcard CORS origin ('*') is not allowed because the API sends "
                "credentials; configure explicit CORS_ORIGINS."
            )

        if app_env == "production":
            if self.auth_mode != AuthenticationMode.ENTRA_OIDC:
                errors.append(
                    "Production requires AUTH_MODE=entra_oidc; "
                    f"local_development/test modes are forbidden (got {self.auth_mode.value})."
                )
            if not self.entra_issuer.strip():
                errors.append("Production requires ENTRA_ISSUER.")
            if not self.entra_audience.strip():
                errors.append("Production requires ENTRA_AUDIENCE.")
            if not self.entra_jwks_uri.strip():
                errors.append("Production requires ENTRA_JWKS_URI.")
            if not self.entra_allowed_tenant_ids:
                errors.append("Production requires at least one ENTRA_ALLOWED_TENANT_IDS entry.")
            if self.local_auth_secret:
                errors.append(
                    "SIGNALFORGE_LOCAL_AUTH_SECRET must not be configured in production "
                    "(local development token signing is disabled there)."
                )
            if self.docs_enabled:
                errors.append("DOCS_ENABLED must be false in production.")
            if not self.trusted_hosts or "*" in self.trusted_hosts:
                errors.append("Production requires explicit non-wildcard TRUSTED_HOSTS.")

        if self.auth_mode == AuthenticationMode.LOCAL_DEVELOPMENT and self.local_auth_secret:
            if not self.local_auth_secret_is_strong():
                errors.append(
                    "SIGNALFORGE_LOCAL_AUTH_SECRET must be at least "
                    f"{MIN_LOCAL_AUTH_SECRET_LENGTH} characters."
                )

        if errors:
            raise SecurityConfigError("; ".join(errors))


@lru_cache
def get_security_settings() -> SecuritySettings:
    return SecuritySettings()


def validate_startup_security() -> SecuritySettings:
    """Resolve and validate security settings against the app environment.

    Called at application startup. Raises on unsafe configuration so production
    deployments fail closed rather than serving unauthenticated traffic.
    """
    app_settings = get_settings()
    security = get_security_settings()
    security.validate_for_environment(app_settings.app_env, app_settings.cors_origins)
    return security
