"""Production-safe configuration / fail-closed startup tests (Prompt 7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.security.config import SecuritySettings, get_security_settings
from app.security.exceptions import SecurityConfigError


def _settings(**overrides) -> SecuritySettings:
    get_security_settings.cache_clear()
    return SecuritySettings(**overrides)


def _prod_ready(**overrides) -> SecuritySettings:
    base = {
        "AUTH_MODE": "entra_oidc",
        "ENTRA_ISSUER": "https://login.microsoftonline.com/guid/v2.0",
        "ENTRA_AUDIENCE": "api://signalforge",
        "ENTRA_JWKS_URI": "https://login.microsoftonline.com/guid/discovery/v2.0/keys",
        "ENTRA_ALLOWED_TENANT_IDS": "guid",
        "DOCS_ENABLED": "false",
        "TRUSTED_HOSTS": "api.signalforge.example",
    }
    base.update(overrides)
    return _settings(**base)


def test_wildcard_cors_with_credentials_rejected():
    settings = _prod_ready()
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("development", ["*"])


def test_production_ready_config_passes():
    settings = _prod_ready()
    settings.validate_for_environment("production", ["https://app.signalforge.example"])


def test_production_missing_issuer_rejected():
    settings = _prod_ready(ENTRA_ISSUER="")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_production_missing_audience_rejected():
    settings = _prod_ready(ENTRA_AUDIENCE="")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_production_test_mode_rejected():
    settings = _prod_ready(AUTH_MODE="test")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_production_local_dev_mode_rejected():
    settings = _prod_ready(AUTH_MODE="local_development")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_production_docs_enabled_rejected():
    settings = _prod_ready(DOCS_ENABLED="true")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_production_wildcard_trusted_host_rejected():
    settings = _prod_ready(TRUSTED_HOSTS="*")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_production_local_secret_present_rejected():
    settings = _prod_ready(SIGNALFORGE_LOCAL_AUTH_SECRET="x" * 40)
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("production", ["https://app.example"])


def test_weak_local_secret_rejected():
    settings = _settings(AUTH_MODE="local_development", SIGNALFORGE_LOCAL_AUTH_SECRET="short")
    with pytest.raises(SecurityConfigError):
        settings.validate_for_environment("development", ["http://localhost:3000"])


def test_invalid_clock_skew_rejected():
    with pytest.raises(ValidationError):
        _settings(JWT_CLOCK_SKEW_SECONDS="9999")


def test_invalid_dev_ttl_rejected():
    with pytest.raises(ValidationError):
        _settings(LOCAL_DEV_TOKEN_TTL_SECONDS="5")


@pytest.fixture(autouse=True)
def _restore():
    yield
    get_security_settings.cache_clear()
