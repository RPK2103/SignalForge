"""Resolve an authenticated principal into a per-request SecurityContext.

Tenant selection rules (Prompt 7 section 13):
- a verified principal must be established first;
- the selected tenant must be one of the principal's ACTIVE memberships;
- ``X-SignalForge-Tenant-ID`` acts only as a selector after authentication and
  never grants membership;
- a token tenant claim may select the tenant when unambiguous;
- foreign and nonexistent tenants are externally indistinguishable (404).

Two resolution strategies:
- ``entra_oidc`` (production): memberships and roles come from the database
  (``SecurityPrincipal`` + ``RoleAssignment``);
- ``local_development`` / ``test``: memberships and roles come from the signed
  token claims (no database round-trip required for local iteration and tests).
"""

from __future__ import annotations

from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import InvalidTenantContextError, normalize_tenant_id
from app.security.context import SecurityContext
from app.security.enums import AuthenticationMode, PrincipalStatus
from app.security.exceptions import TenantSelectionError
from app.security.permissions import permissions_for_roles, resolve_roles
from app.security.principal import AuthenticatedPrincipal

_WILDCARD_MEMBERSHIP = "*"


class SecurityContextResolver:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def resolve(
        self,
        principal: AuthenticatedPrincipal,
        *,
        requested_tenant: str | None,
        correlation_id: str,
    ) -> SecurityContext:
        if principal.authentication_mode == AuthenticationMode.ENTRA_OIDC:
            return self._resolve_from_database(principal, requested_tenant, correlation_id)
        return self._resolve_from_claims(principal, requested_tenant, correlation_id)

    # -- claims-based (dev/test) -------------------------------------------
    def _resolve_from_claims(
        self,
        principal: AuthenticatedPrincipal,
        requested_tenant: str | None,
        correlation_id: str,
    ) -> SecurityContext:
        memberships = principal.claimed_tenant_memberships or (principal.external_tenant_id,)
        wildcard = _WILDCARD_MEMBERSHIP in memberships

        selected = requested_tenant or principal.claimed_tenant_selector
        if selected is None:
            concrete = [m for m in memberships if m != _WILDCARD_MEMBERSHIP]
            if len(concrete) == 1:
                selected = concrete[0]
        if selected is None:
            raise TenantSelectionError("No tenant selected")

        try:
            selected = normalize_tenant_id(selected)
        except InvalidTenantContextError as exc:
            raise TenantSelectionError("Invalid tenant selection") from exc

        normalized_memberships = {
            normalize_tenant_id(m) for m in memberships if m != _WILDCARD_MEMBERSHIP
        }
        if not wildcard and selected not in normalized_memberships:
            # Foreign/nonexistent tenants look identical externally.
            raise TenantSelectionError("Tenant not accessible")

        roles = resolve_roles(principal.claimed_roles)
        permissions = permissions_for_roles(roles)
        return SecurityContext(
            principal=principal,
            tenant_id=selected,
            roles=roles,
            permissions=permissions,
            correlation_id=correlation_id,
            authentication_mode=principal.authentication_mode,
            principal_id=principal.subject,
        )

    # -- database-based (production) ---------------------------------------
    def _resolve_from_database(
        self,
        principal: AuthenticatedPrincipal,
        requested_tenant: str | None,
        correlation_id: str,
    ) -> SecurityContext:
        if requested_tenant is None:
            raise TenantSelectionError("No tenant selected")
        try:
            selected = normalize_tenant_id(requested_tenant)
        except InvalidTenantContextError as exc:
            raise TenantSelectionError("Invalid tenant selection") from exc

        principal_row = self._uow.security_principals.find_by_subject(selected, principal.subject)
        # Membership is proven only by an ACTIVE principal row in the selected
        # tenant. A missing or deactivated principal is indistinguishable from a
        # nonexistent tenant.
        if principal_row is None or principal_row.status != PrincipalStatus.ACTIVE.value:
            raise TenantSelectionError("Tenant not accessible")

        roles = self._uow.role_assignments.active_roles(selected, principal_row.id)
        permissions = permissions_for_roles(roles)
        return SecurityContext(
            principal=principal,
            tenant_id=selected,
            roles=roles,
            permissions=permissions,
            correlation_id=correlation_id,
            authentication_mode=principal.authentication_mode,
            principal_id=principal_row.id,
        )
