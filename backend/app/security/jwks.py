"""Bounded JWKS retrieval and caching (Phase 3 Prompt 7).

- configurable TTL;
- refresh on unknown key ID (bounded, single retry);
- bounded response size and request timeout;
- safe provider-failure categories;
- NEVER logs the token or the full JWKS payload.

Unit tests inject a fake ``JwksClient`` so no network access is required.
"""

from __future__ import annotations

import time
from typing import Protocol

import httpx
import jwt

from app.security.enums import AuthenticationFailureCategory

_MAX_CACHED_KEYS = 32


class JwksProviderError(Exception):
    """Raised when JWKS could not be retrieved or parsed safely."""

    def __init__(self, category: AuthenticationFailureCategory, detail: str) -> None:
        super().__init__(detail)
        self.category = category
        self.detail = detail


class JwksClient(Protocol):
    """Fetches a JWKS document and returns its ``keys`` list of JWK dicts."""

    def fetch(self, uri: str) -> list[dict]: ...


class HttpxJwksClient:
    """Production JWKS client with bounded time and response size."""

    def __init__(self, *, timeout_seconds: float, max_response_bytes: int) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_response_bytes

    def fetch(self, uri: str) -> list[dict]:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(uri)
        except httpx.TimeoutException as exc:
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_UNAVAILABLE, "jwks request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_UNAVAILABLE, "jwks request failed"
            ) from exc
        if response.status_code != 200:
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_UNAVAILABLE,
                f"jwks endpoint returned status {response.status_code}",
            )
        raw = response.content
        if len(raw) > self._max_bytes:
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_MALFORMED, "jwks response too large"
            )
        try:
            document = response.json()
        except ValueError as exc:
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_MALFORMED, "jwks response was not valid json"
            ) from exc
        keys = document.get("keys") if isinstance(document, dict) else None
        if not isinstance(keys, list):
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_MALFORMED, "jwks response missing keys array"
            )
        return keys


class BoundedJwksCache:
    """Caches parsed signing keys per JWKS URI with a bounded TTL and size."""

    def __init__(
        self,
        client: JwksClient,
        *,
        ttl_seconds: int,
        max_keys: int = _MAX_CACHED_KEYS,
        clock=time.monotonic,
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None

    def _is_expired(self) -> bool:
        return self._fetched_at is None or (self._clock() - self._fetched_at) >= self._ttl

    def _load(self, uri: str) -> None:
        raw_keys = self._client.fetch(uri)
        parsed: dict[str, jwt.PyJWK] = {}
        for jwk in raw_keys[: self._max_keys]:
            kid = jwk.get("kid") if isinstance(jwk, dict) else None
            if not kid:
                continue
            try:
                parsed[str(kid)] = jwt.PyJWK.from_dict(jwk)
            except (jwt.PyJWKError, jwt.InvalidKeyError, ValueError, KeyError):
                # Skip an individual malformed key rather than failing the whole set.
                continue
        if not parsed:
            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_MALFORMED, "jwks contained no usable keys"
            )
        self._keys = parsed
        self._fetched_at = self._clock()

    def get_signing_key(self, uri: str, kid: str) -> jwt.PyJWK:
        """Return the signing key for ``kid``, refreshing once on a cache miss."""
        if self._is_expired() or not self._keys:
            self._load(uri)
        key = self._keys.get(kid)
        if key is None:
            # Unknown key id -> force a single refresh (handles key rotation).
            self._load(uri)
            key = self._keys.get(kid)
        if key is None:
            raise JwksProviderError(
                AuthenticationFailureCategory.UNKNOWN_KEY_ID, "signing key id not found"
            )
        return key
