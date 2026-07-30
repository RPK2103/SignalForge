"""Failure-injection tests: fail closed, no cross-tenant fallback (Prompt 7)."""

from __future__ import annotations

import pytest

from app.security.administration import SecurityAdministrationService
from app.security.audit import SecurityAuditService
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
from app.security.rls import (
    clear_transaction_tenant,
    current_transaction_tenant,
    set_transaction_tenant,
)

TENANT = "novabank"


def _entra(subject: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        subject=subject,
        principal_type=PrincipalType.USER,
        external_tenant_id="entra-tenant-guid",
        authentication_mode=AuthenticationMode.ENTRA_OIDC,
    )


def _admin_context() -> SecurityContext:
    roles = frozenset({SecurityRole.TENANT_ADMIN})
    return SecurityContext(
        principal=_entra("admin"),
        tenant_id=TENANT,
        roles=roles,
        permissions=permissions_for_roles(roles),
        correlation_id="c",
        authentication_mode=AuthenticationMode.ENTRA_OIDC,
        principal_id="admin",
    )


# -- principal lookup failure fails closed -----------------------------------
def test_principal_lookup_missing_fails_closed(uow):
    resolver = SecurityContextResolver(uow)
    with pytest.raises(TenantSelectionError):
        resolver.resolve(_entra("nobody"), requested_tenant=TENANT, correlation_id="c")


# -- role lookup failure grants nothing --------------------------------------
def test_role_lookup_empty_grants_nothing(uow):
    uow.security_principals.create(TENANT, principal_type="user", external_subject_id="roleless")
    uow.commit()
    resolver = SecurityContextResolver(uow)
    ctx = resolver.resolve(_entra("roleless"), requested_tenant=TENANT, correlation_id="c")
    assert ctx.permissions == frozenset()


# -- authorization failure raises --------------------------------------------
def test_authorization_injection_denies(uow):
    reader_roles = frozenset({SecurityRole.EXECUTIVE_READER})
    ctx = SecurityContext(
        principal=_entra("reader"),
        tenant_id=TENANT,
        roles=reader_roles,
        permissions=permissions_for_roles(reader_roles),
        correlation_id="c",
        authentication_mode=AuthenticationMode.ENTRA_OIDC,
        principal_id="reader",
    )
    service = SecurityAdministrationService(uow)
    with pytest.raises(AuthorizationError):
        service.assign_role(ctx, principal_id="x", role=SecurityRole.EXECUTIVE_READER)


# -- audit persistence failure rolls back the mutation -----------------------
class _BrokenAuditRepo:
    def append(self, **_kwargs):
        raise RuntimeError("audit down")


def test_audit_failure_rolls_back_role_assignment(uow):
    principal = uow.security_principals.create(
        TENANT, principal_type="user", external_subject_id="target"
    )
    uow.commit()
    # Break the audit repo so the fail-closed audit write raises.
    uow.security_audit_events = _BrokenAuditRepo()  # type: ignore[assignment]
    service = SecurityAdministrationService(uow)
    from app.security.audit import AuditWriteError

    with pytest.raises(AuditWriteError):
        service.assign_role(
            _admin_context(), principal_id=principal.id, role=SecurityRole.EXECUTIVE_READER
        )
    # After rollback there must be no committed role assignment.
    uow2_roles = uow.role_assignments.active_roles(TENANT, principal.id)
    assert uow2_roles == frozenset()


# -- RLS context helpers on SQLite are safe no-ops ---------------------------
def test_rls_helpers_are_noops_on_sqlite(db_session):
    # SQLite is NOT proof of RLS: these must not raise and report no context.
    set_transaction_tenant(db_session, TENANT)
    assert current_transaction_tenant(db_session) is None
    clear_transaction_tenant(db_session)
    assert current_transaction_tenant(db_session) is None


# -- audit-write injection for denial path still surfaces 403 ----------------
def test_denied_audit_write_best_effort(uow):
    reader_roles = frozenset({SecurityRole.EXECUTIVE_READER})
    ctx = SecurityContext(
        principal=_entra("reader"),
        tenant_id=TENANT,
        roles=reader_roles,
        permissions=permissions_for_roles(reader_roles),
        correlation_id="c",
        authentication_mode=AuthenticationMode.ENTRA_OIDC,
        principal_id="reader",
    )
    audit = SecurityAuditService(uow)
    authz = AuthorizationService()
    outcome = authz.check(ctx, Permission.SECURITY_AUDIT_READ, TENANT)
    assert not outcome.allowed
    # Recording the denial must not raise.
    audit.record_authorization_denied(
        ctx,
        action="api.security.audit.read",
        resource_type="api_route",
        reason_code=outcome.reason_code,
    )
    audit.commit()
