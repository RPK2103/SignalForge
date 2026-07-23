import pytest

from app.core.config import get_settings
from app.services.ai_service import get_azure_openai_client

pytest_plugins = ["tests.persistence.conftest"]

_AZURE_ENV_KEYS = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AI_ENABLED", "false")
    for key in _AZURE_ENV_KEYS:
        monkeypatch.setenv(key, "")

    get_settings.cache_clear()
    get_azure_openai_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_azure_openai_client.cache_clear()
