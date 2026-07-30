"""Process-lifetime security providers (Phase 3 Prompt 7).

Caches the authentication service (and, for Entra mode, its bounded JWKS cache)
across requests. Tests clear these caches alongside the settings caches.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.security.authentication import AuthenticationService
from app.security.config import get_security_settings


@lru_cache
def get_authentication_service() -> AuthenticationService:
    settings = get_settings()
    security = get_security_settings()
    return AuthenticationService(security, settings.app_env)


def reset_security_providers() -> None:
    get_authentication_service.cache_clear()
