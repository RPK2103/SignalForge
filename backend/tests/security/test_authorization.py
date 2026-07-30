"""Service-layer authorization + tenant selection tests (Phase 3 Prompt 7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.context_resolver import SecurityContextResolver
from app.security.enums import (
    AuthenticationMode,
    Permission,
    PrincipalType,
    SecurityRole,
)
from app.security.exceptions import AuthorizationError, TenantSelectionError
from app.security.permissions import permissions_for_roles
from app.security.principal import AuthenticatedPrincipal

TENANT_A = "novabank"
TENANT_B = "acmecorp"


def _context(tenant: str, roles: frozenset[SecurityRole]) -> SecurityContext:
    return SecurityContext(
        principal=AuthenticatedPrincipal(
            subject="s",
            principal_type=PrincipalType.USER,
            external_tenant_id=tenant,
            authentication_mode=AuthenticationMode.TEST,
        ),
        tenant_id=tenant,
        roles=roles,
        permissions=permissions_for_roles(roles),
        correlation_id="corr-1",
        authentication_mode=AuthenticationMode.TEST,
        principal_id="p1",
    )


def _entra_principal(subject: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        subject=subject,
        principal_type=PrincipalType.USER,
        external_tenant_id="entra-tenant-guid",
        authentication_mode=AuthenticationMode.ENTRA_OIDC,
    )


# -- direct service authorization --------------------------------------------
def test_no_context_fails_closed():
    authz = AuthorizationService()
    outcome = authz.check(None, Permission.ENTERPRISE_READ, TENANT_A)
    assert not outcome.allowed
    with pytest.raises(AuthorizationError):
        authz.require(None, Permission.ENTERPRISE_READ, TENANT_A)


def test_missing_permission_denied():
    authz = AuthorizationService()
    ctx = _context(TENANT_A, frozenset({SecurityRole.EXECUTIVE_READER}))
    with pytest.raises(AuthorizationError):
        authz.require(ctx, Permission.PREDICTIONS_PROMOTE, TENANT_A)


def test_tenant_mismatch_denied():
    authz = AuthorizationService()
    ctx = _context(TENANT_A, frozenset({SecurityRole.TENANT_ADMIN}))
    outcome = authz.check(ctx, Permission.ENTERPRISE_READ, TENANT_B)
    assert not outcome.allowed
    assert outcome.reason_code == "tenant_mismatch"


def test_granted_permission_allows():
    authz = AuthorizationService()
    ctx = _context(TENANT_A, frozenset({SecurityRole.EXECUTIVE_READER}))
    authz.require(ctx, Permission.ENTERPRISE_READ, TENANT_A)


# -- DB-backed resolution (entra mode) ---------------------------------------
def test_active_principal_resolves_roles(uow):
    principal = uow.security_principals.create(
        TENANT_A, principal_type="user", external_subject_id="db-user"
    )
    uow.role_assignments.assign(TENANT_A, principal_id=principal.id, role="executive_reader")
    uow.commit()

    resolver = SecurityContextResolver(uow)
    ctx = resolver.resolve(
        _entra_principal("db-user"), requested_tenant=TENANT_A, correlation_id="c"
    )
    assert SecurityRole.EXECUTIVE_READER in ctx.roles
    assert Permission.ENTERPRISE_READ in ctx.permissions


def test_expired_assignment_grants_nothing(uow):
    principal = uow.security_principals.create(
        TENANT_A, principal_type="user", external_subject_id="expired-user"
    )
    past = datetime.now(timezone.utc) - timedelta(days=1)
    uow.role_assignments.assign(
        TENANT_A,
        principal_id=principal.id,
        role="tenant_admin",
        valid_from=past - timedelta(days=1),
        valid_to=past,
    )
    uow.commit()

    resolver = SecurityContextResolver(uow)
    ctx = resolver.resolve(
        _entra_principal("expired-user"), requested_tenant=TENANT_A, correlation_id="c"
    )
    assert ctx.roles == frozenset()
    assert ctx.permissions == frozenset()


def test_deactivated_principal_is_inaccessible(uow):
    principal = uow.security_principals.create(
        TENANT_A, principal_type="user", external_subject_id="dead-user"
    )
    uow.role_assignments.assign(TENANT_A, principal_id=principal.id, role="tenant_admin")
    uow.security_principals.deactivate(TENANT_A, principal.id)
    uow.commit()

    resolver = SecurityContextResolver(uow)
    with pytest.raises(TenantSelectionError):
        resolver.resolve(
            _entra_principal("dead-user"), requested_tenant=TENANT_A, correlation_id="c"
        )


def test_foreign_tenant_selector_is_inaccessible(uow):
    principal = uow.security_principals.create(
        TENANT_A, principal_type="user", external_subject_id="tenant-a-user"
    )
    uow.role_assignments.assign(TENANT_A, principal_id=principal.id, role="tenant_admin")
    uow.commit()

    resolver = SecurityContextResolver(uow)
    # Same subject, but selecting a tenant where no principal row exists.
    with pytest.raises(TenantSelectionError):
        resolver.resolve(
            _entra_principal("tenant-a-user"), requested_tenant=TENANT_B, correlation_id="c"
        )


def test_unknown_subject_is_inaccessible(uow):
    resolver = SecurityContextResolver(uow)
    with pytest.raises(TenantSelectionError):
        resolver.resolve(_entra_principal("ghost"), requested_tenant=TENANT_A, correlation_id="c")


# -- claims-based tenant selection (dev/test) --------------------------------
def test_claims_wildcard_membership_allows_any_tenant():
    resolver = SecurityContextResolver(uow=None)  # type: ignore[arg-type]
    principal = AuthenticatedPrincipal(
        subject="dev",
        principal_type=PrincipalType.USER,
        external_tenant_id="novabank",
        authentication_mode=AuthenticationMode.TEST,
        claimed_roles=("tenant_admin",),
        claimed_tenant_memberships=("*",),
    )
    ctx = resolver.resolve(principal, requested_tenant="whatever", correlation_id="c")
    assert ctx.tenant_id == "whatever"


def test_claims_foreign_tenant_selector_rejected():
    resolver = SecurityContextResolver(uow=None)  # type: ignore[arg-type]
    principal = AuthenticatedPrincipal(
        subject="dev",
        principal_type=PrincipalType.USER,
        external_tenant_id="novabank",
        authentication_mode=AuthenticationMode.TEST,
        claimed_roles=("executive_reader",),
        claimed_tenant_memberships=("novabank",),
    )
    with pytest.raises(TenantSelectionError):
        resolver.resolve(principal, requested_tenant="acmecorp", correlation_id="c")
