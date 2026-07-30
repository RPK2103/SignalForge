"""JWT verification behind a provider-independent protocol (Prompt 7).

``EntraJwtVerifier`` validates Microsoft Entra-compatible RS256 tokens against a
JWKS. ``SymmetricJwtVerifier`` backs the ``local_development`` and ``test`` modes
with signed short-lived HS256 tokens. All verifiers translate raw tokens into the
domain :class:`AuthenticationResult` — no PyJWT types leak upward.

Security rules enforced here:
- explicit algorithm allowlist (never ``none`` / caller-selected algorithm);
- issuer and audience are fixed by configuration, never caller-selected;
- expiration, not-before and a stable subject are required;
- Entra tenant claim must be an explicitly configured tenant;
- tokens above a byte bound are rejected before parsing;
- no raw token or signature is ever logged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import jwt

from app.security.enums import (
    AuthenticationFailureCategory,
    AuthenticationMode,
    PrincipalType,
)
from app.security.jwks import BoundedJwksCache, JwksProviderError
from app.security.principal import (
    AuthenticatedPrincipal,
    AuthenticationResult,
    TokenClaims,
)

_ALG_NONE = {"none", "None", "NONE"}


def _to_dt(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _principal_type_from_claims(payload: dict) -> PrincipalType:
    idtyp = str(payload.get("idtyp", "")).lower()
    if idtyp == "app":
        return PrincipalType.SERVICE_PRINCIPAL
    ptyp = str(payload.get("ptyp", "")).lower()
    if ptyp == PrincipalType.SERVICE_PRINCIPAL.value:
        return PrincipalType.SERVICE_PRINCIPAL
    # An app-only token (appid without a user subject scope) is a service principal.
    if payload.get("appid") and not payload.get("name") and not payload.get("preferred_username"):
        return PrincipalType.SERVICE_PRINCIPAL
    return PrincipalType.USER


def _as_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


class JwtVerifier(Protocol):
    def verify(self, token: str) -> AuthenticationResult: ...


def _decode_unverified_header(token: str) -> dict:
    return jwt.get_unverified_header(token)


class EntraJwtVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        allowed_tenant_ids: tuple[str, ...],
        allowed_algorithms: tuple[str, ...],
        jwks_uri: str,
        jwks_cache: BoundedJwksCache,
        clock_skew_seconds: int,
        max_token_bytes: int,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._allowed_tenants = frozenset(allowed_tenant_ids)
        self._allowed_algorithms = tuple(allowed_algorithms)
        self._jwks_uri = jwks_uri
        self._jwks_cache = jwks_cache
        self._skew = clock_skew_seconds
        self._max_bytes = max_token_bytes

    def verify(self, token: str) -> AuthenticationResult:
        if not token:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MISSING_TOKEN)
        if len(token.encode("utf-8")) > self._max_bytes:
            return AuthenticationResult.failure(AuthenticationFailureCategory.TOKEN_TOO_LARGE)

        try:
            header = _decode_unverified_header(token)
        except jwt.InvalidTokenError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MALFORMED_TOKEN)

        alg = str(header.get("alg", ""))
        if alg in _ALG_NONE or not alg:
            return AuthenticationResult.failure(
                AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM, "algorithm not permitted"
            )
        if alg not in self._allowed_algorithms:
            return AuthenticationResult.failure(
                AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM, "algorithm not allowlisted"
            )
        kid = header.get("kid")
        if not kid:
            return AuthenticationResult.failure(AuthenticationFailureCategory.UNKNOWN_KEY_ID)

        try:
            signing_key = self._jwks_cache.get_signing_key(self._jwks_uri, str(kid))
        except JwksProviderError as exc:
            return AuthenticationResult.failure(exc.category, exc.detail)

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._allowed_algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._skew,
                options={
                    "require": ["exp", "iat", "nbf", "sub", "aud", "iss"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.ExpiredSignatureError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.EXPIRED)
        except jwt.ImmatureSignatureError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.NOT_YET_VALID)
        except jwt.InvalidIssuerError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.INVALID_ISSUER)
        except jwt.InvalidAudienceError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.INVALID_AUDIENCE)
        except jwt.InvalidAlgorithmError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM)
        except jwt.MissingRequiredClaimError as exc:
            claim = getattr(exc, "claim", "")
            if claim == "sub":
                return AuthenticationResult.failure(AuthenticationFailureCategory.MISSING_SUBJECT)
            return AuthenticationResult.failure(AuthenticationFailureCategory.MALFORMED_TOKEN)
        except jwt.InvalidSignatureError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.INVALID_SIGNATURE)
        except jwt.InvalidTokenError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MALFORMED_TOKEN)

        subject = str(payload.get("sub") or payload.get("oid") or "").strip()
        if not subject:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MISSING_SUBJECT)

        external_tenant = str(payload.get("tid") or "").strip()
        if not external_tenant or external_tenant not in self._allowed_tenants:
            return AuthenticationResult.failure(AuthenticationFailureCategory.UNKNOWN_TENANT)

        principal_type = _principal_type_from_claims(payload)
        application_id = str(payload.get("appid") or payload.get("azp") or "") or None
        claims = TokenClaims(
            subject=subject,
            issuer=self._issuer,
            audience=self._audience,
            external_tenant_id=external_tenant,
            principal_type=principal_type,
            key_id=str(kid),
            application_id=application_id,
            display_label=str(payload.get("name") or "") or None,
            issued_at=_to_dt(payload.get("iat")),
            not_before=_to_dt(payload.get("nbf")),
            expires_at=_to_dt(payload.get("exp")),
        )
        principal = AuthenticatedPrincipal(
            subject=subject,
            principal_type=principal_type,
            external_tenant_id=external_tenant,
            authentication_mode=AuthenticationMode.ENTRA_OIDC,
            application_id=application_id,
            display_label=claims.display_label,
        )
        return AuthenticationResult.success(principal, claims)


class SymmetricJwtVerifier:
    """HS256 verifier for ``local_development`` and ``test`` modes.

    Our own dev/test tokens additionally carry ``roles``, ``tenants`` and an
    optional ``tenant`` selector claim so the claims-based context resolver can
    build a :class:`SecurityContext` without a database round-trip.
    """

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str,
        mode: AuthenticationMode,
        clock_skew_seconds: int,
        max_token_bytes: int,
        algorithm: str = "HS256",
    ) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._mode = mode
        self._skew = clock_skew_seconds
        self._max_bytes = max_token_bytes
        self._algorithm = algorithm

    def verify(self, token: str) -> AuthenticationResult:
        if not token:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MISSING_TOKEN)
        if not self._secret:
            return AuthenticationResult.failure(
                AuthenticationFailureCategory.MODE_NOT_PERMITTED,
                "signing secret not configured",
            )
        if len(token.encode("utf-8")) > self._max_bytes:
            return AuthenticationResult.failure(AuthenticationFailureCategory.TOKEN_TOO_LARGE)

        try:
            header = _decode_unverified_header(token)
        except jwt.InvalidTokenError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MALFORMED_TOKEN)
        alg = str(header.get("alg", ""))
        if alg in _ALG_NONE or alg != self._algorithm:
            return AuthenticationResult.failure(AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM)

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._skew,
                options={
                    "require": ["exp", "sub", "aud", "iss"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.ExpiredSignatureError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.EXPIRED)
        except jwt.ImmatureSignatureError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.NOT_YET_VALID)
        except jwt.InvalidIssuerError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.INVALID_ISSUER)
        except jwt.InvalidAudienceError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.INVALID_AUDIENCE)
        except jwt.InvalidSignatureError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.INVALID_SIGNATURE)
        except jwt.InvalidTokenError:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MALFORMED_TOKEN)

        subject = str(payload.get("sub") or "").strip()
        if not subject:
            return AuthenticationResult.failure(AuthenticationFailureCategory.MISSING_SUBJECT)
        external_tenant = str(payload.get("tid") or "").strip()
        if not external_tenant:
            return AuthenticationResult.failure(AuthenticationFailureCategory.UNKNOWN_TENANT)

        try:
            principal_type = PrincipalType(str(payload.get("ptyp", PrincipalType.USER.value)))
        except ValueError:
            principal_type = PrincipalType.USER

        roles = _as_tuple(payload.get("roles"))
        memberships = _as_tuple(payload.get("tenants")) or (external_tenant,)
        selector = str(payload.get("tenant") or "") or None
        application_id = str(payload.get("appid") or "") or None
        display = str(payload.get("name") or "") or None

        claims = TokenClaims(
            subject=subject,
            issuer=self._issuer,
            audience=self._audience,
            external_tenant_id=external_tenant,
            principal_type=principal_type,
            application_id=application_id,
            roles=roles,
            tenant_memberships=memberships,
            tenant_selector=selector,
            display_label=display,
            issued_at=_to_dt(payload.get("iat")),
            not_before=_to_dt(payload.get("nbf")),
            expires_at=_to_dt(payload.get("exp")),
        )
        principal = AuthenticatedPrincipal(
            subject=subject,
            principal_type=principal_type,
            external_tenant_id=external_tenant,
            authentication_mode=self._mode,
            application_id=application_id,
            display_label=display,
            claimed_roles=roles,
            claimed_tenant_memberships=memberships,
            claimed_tenant_selector=selector,
        )
        return AuthenticationResult.success(principal, claims)
