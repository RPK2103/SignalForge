"""Authentication service: raw bearer token -> verified principal (Prompt 7).

Selects a provider verifier by the configured :class:`AuthenticationMode` and
enforces environment rules fail-closed:
- production must use ``entra_oidc``;
- ``local_development`` is impossible in production;
- ``test`` is impossible outside the test environment.
"""

from __future__ import annotations

from app.core.config import AppEnv
from app.security.config import SecuritySettings
from app.security.enums import AuthenticationFailureCategory, AuthenticationMode
from app.security.jwks import BoundedJwksCache, HttpxJwksClient, JwksClient
from app.security.jwt_verifier import (
    EntraJwtVerifier,
    JwtVerifier,
    SymmetricJwtVerifier,
)
from app.security.principal import AuthenticationResult

# A distinct fixed issuer/audience/secret space for the in-process test mode so a
# test token can never be confused with a local-development or Entra token.
TEST_ISSUER = "signalforge-test"
TEST_AUDIENCE = "signalforge-test-api"
TEST_SECRET = "signalforge-test-secret-key-do-not-use-in-production-0001"


class AuthenticationService:
    def __init__(
        self,
        settings: SecuritySettings,
        app_env: AppEnv,
        *,
        jwks_client: JwksClient | None = None,
        jwks_cache: BoundedJwksCache | None = None,
    ) -> None:
        self._settings = settings
        self._app_env = app_env
        self._jwks_client = jwks_client
        self._jwks_cache = jwks_cache
        self._verifier: JwtVerifier | None = None

    def _mode_permitted(self) -> bool:
        mode = self._settings.auth_mode
        if self._app_env == "production":
            return mode == AuthenticationMode.ENTRA_OIDC
        if mode == AuthenticationMode.TEST:
            # Test mode is only permitted when the app environment is not a real
            # deployment environment. The pytest harness runs with development.
            return self._app_env != "production"
        return True

    def _build_verifier(self) -> JwtVerifier:
        settings = self._settings
        mode = settings.auth_mode
        if mode == AuthenticationMode.ENTRA_OIDC:
            cache = self._jwks_cache
            if cache is None:
                client = self._jwks_client or HttpxJwksClient(
                    timeout_seconds=settings.jwks_request_timeout_seconds,
                    max_response_bytes=settings.jwks_max_response_bytes,
                )
                cache = BoundedJwksCache(client, ttl_seconds=settings.jwks_cache_ttl_seconds)
            return EntraJwtVerifier(
                issuer=settings.entra_issuer,
                audience=settings.entra_audience,
                allowed_tenant_ids=tuple(settings.entra_allowed_tenant_ids),
                allowed_algorithms=settings.entra_allowed_algorithms,
                jwks_uri=settings.entra_jwks_uri,
                jwks_cache=cache,
                clock_skew_seconds=settings.jwt_clock_skew_seconds,
                max_token_bytes=settings.max_token_bytes,
            )
        if mode == AuthenticationMode.LOCAL_DEVELOPMENT:
            return SymmetricJwtVerifier(
                secret=settings.local_auth_secret,
                issuer=settings.local_dev_issuer,
                audience=settings.local_dev_audience,
                mode=AuthenticationMode.LOCAL_DEVELOPMENT,
                clock_skew_seconds=settings.jwt_clock_skew_seconds,
                max_token_bytes=settings.max_token_bytes,
            )
        # test mode
        return SymmetricJwtVerifier(
            secret=TEST_SECRET,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            mode=AuthenticationMode.TEST,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
            max_token_bytes=settings.max_token_bytes,
        )

    def authenticate(self, token: str | None) -> AuthenticationResult:
        if not self._mode_permitted():
            return AuthenticationResult.failure(
                AuthenticationFailureCategory.MODE_NOT_PERMITTED,
                "authentication mode not permitted in this environment",
            )
        if token is None or not token.strip():
            return AuthenticationResult.failure(AuthenticationFailureCategory.MISSING_TOKEN)
        if self._verifier is None:
            self._verifier = self._build_verifier()
        return self._verifier.verify(token.strip())
