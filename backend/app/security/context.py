"""Immutable per-request security context (Phase 3 Prompt 7).

A ``SecurityContext`` is resolved once per request (or per CLI operation) and
threaded explicitly. There is deliberately NO hidden global mutable principal:
authorization always consults the context passed to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.security.enums import AuthenticationMode, Permission, PrincipalType, SecurityRole
from app.security.principal import AuthenticatedPrincipal


@dataclass(frozen=True, slots=True)
class SecurityContext:
    principal: AuthenticatedPrincipal
    tenant_id: str
    roles: frozenset[SecurityRole]
    permissions: frozenset[Permission]
    correlation_id: str
    authentication_mode: AuthenticationMode
    principal_id: str | None = None
    is_internal_system: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions

    @property
    def subject(self) -> str:
        return self.principal.subject


INTERNAL_SYSTEM_SUBJECT = "internal-system"


def internal_system_context(
    tenant_id: str,
    *,
    correlation_id: str,
    permissions: frozenset[Permission] | None = None,
    roles: frozenset[SecurityRole] | None = None,
) -> SecurityContext:
    """Explicitly trusted internal execution context for CLI/batch operations.

    Even trusted contexts must still pass through ``AuthorizationService`` for
    permission-sensitive operations; this simply grants an explicit, auditable
    internal identity rather than a hidden bypass.
    """
    granted_roles = roles if roles is not None else frozenset({SecurityRole.TENANT_ADMIN})
    from app.security.permissions import permissions_for_roles

    granted_permissions = (
        permissions if permissions is not None else permissions_for_roles(granted_roles)
    )
    principal = AuthenticatedPrincipal(
        subject=INTERNAL_SYSTEM_SUBJECT,
        principal_type=PrincipalType.SERVICE_PRINCIPAL,
        external_tenant_id=tenant_id,
        authentication_mode=AuthenticationMode.TEST,
    )
    return SecurityContext(
        principal=principal,
        tenant_id=tenant_id,
        roles=granted_roles,
        permissions=granted_permissions,
        correlation_id=correlation_id,
        authentication_mode=AuthenticationMode.TEST,
        principal_id=INTERNAL_SYSTEM_SUBJECT,
        is_internal_system=True,
    )
