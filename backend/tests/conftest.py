import pytest

from app.core.config import get_settings
from app.security.config import get_security_settings
from app.security.providers import reset_security_providers
from app.services.ai_service import get_azure_openai_client

pytest_plugins = ["tests.persistence.conftest"]

_AZURE_ENV_KEYS = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


def _clear_security_caches() -> None:
    get_settings.cache_clear()
    get_security_settings.cache_clear()
    reset_security_providers()
    get_azure_openai_client.cache_clear()


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AI_ENABLED", "false")
    # Default the test suite to the in-process ``test`` authentication mode so the
    # security middleware accepts test-signed JWTs. Security tests override this
    # per-case (e.g. to exercise production fail-closed behaviour).
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "test")
    for key in _AZURE_ENV_KEYS:
        monkeypatch.setenv(key, "")

    _clear_security_caches()
    yield
    _clear_security_caches()
