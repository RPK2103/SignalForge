"""Provider-independent identity value objects (Phase 3 Prompt 7).

No provider SDK types leak into the domain: verifiers translate raw tokens into
these immutable dataclasses, and everything downstream depends only on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.security.enums import (
    AuthenticationFailureCategory,
    AuthenticationMode,
    PrincipalType,
)


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Normalized, secret-safe subset of a verified token's claims.

    NEVER contains the raw token, signature, or private/full claim payload.
    """

    subject: str
    issuer: str
    audience: str
    external_tenant_id: str
    principal_type: PrincipalType
    key_id: str | None = None
    application_id: str | None = None
    roles: tuple[str, ...] = ()
    tenant_memberships: tuple[str, ...] = ()
    tenant_selector: str | None = None
    display_label: str | None = None
    issued_at: datetime | None = None
    not_before: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """A verified caller identity, independent of the underlying provider."""

    subject: str
    principal_type: PrincipalType
    external_tenant_id: str
    authentication_mode: AuthenticationMode
    application_id: str | None = None
    display_label: str | None = None
    # Claim-asserted roles/memberships (used only in dev/test resolver mode).
    claimed_roles: tuple[str, ...] = ()
    claimed_tenant_memberships: tuple[str, ...] = ()
    claimed_tenant_selector: str | None = None


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """Outcome of an authentication attempt (success xor failure)."""

    principal: AuthenticatedPrincipal | None = None
    failure_category: AuthenticationFailureCategory | None = None
    failure_detail: str | None = None
    claims: TokenClaims | None = None
    key_ids_considered: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.principal is not None

    @classmethod
    def success(
        cls, principal: AuthenticatedPrincipal, claims: TokenClaims
    ) -> AuthenticationResult:
        return cls(principal=principal, claims=claims)

    @classmethod
    def failure(
        cls,
        category: AuthenticationFailureCategory,
        detail: str | None = None,
    ) -> AuthenticationResult:
        # NOTE: ``detail`` must never contain token material — callers pass only
        # short, static descriptions.
        return cls(failure_category=category, failure_detail=detail)
