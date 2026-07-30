"""NovaBank synthetic RBAC persona validation (Phase 3 Prompt 7)."""

from __future__ import annotations

import pytest

from app.security.context_resolver import SecurityContextResolver
from app.security.enums import AuthenticationMode, Permission, PrincipalType
from app.security.exceptions import TenantSelectionError
from app.security.novabank_seed import seed_novabank_security
from app.security.principal import AuthenticatedPrincipal

TENANT = "novabank"


@pytest.fixture
def seeded(uow):
    counts = seed_novabank_security(uow, tenant_id=TENANT)
    uow.commit()
    return counts


def _resolve(uow, subject: str, tenant: str = TENANT):
    principal = AuthenticatedPrincipal(
        subject=subject,
        principal_type=PrincipalType.USER,
        external_tenant_id="entra-tenant-guid",
        authentication_mode=AuthenticationMode.ENTRA_OIDC,
    )
    resolver = SecurityContextResolver(uow)
    return resolver.resolve(principal, requested_tenant=tenant, correlation_id="c")


def test_seed_counts(seeded):
    assert seeded["principals"] == 7
    assert seeded["role_assignments"] == 7


def test_executive_reader_reads_but_cannot_generate(seeded, uow):
    ctx = _resolve(uow, "novabank-exec-sub")
    assert ctx.has_permission(Permission.CHIEF_OF_STAFF_READ)
    assert not ctx.has_permission(Permission.CHIEF_OF_STAFF_GENERATE)
    assert not ctx.has_permission(Permission.CHIEF_OF_STAFF_REVIEW)


def test_integration_operator_cannot_promote(seeded, uow):
    ctx = _resolve(uow, "novabank-operator-sub")
    assert ctx.has_permission(Permission.CONNECTORS_SYNC)
    assert not ctx.has_permission(Permission.PREDICTIONS_PROMOTE)


def test_analyst_cannot_manage_security(seeded, uow):
    ctx = _resolve(uow, "novabank-analyst-sub")
    assert ctx.has_permission(Permission.PREDICTIONS_READ)
    assert not ctx.has_permission(Permission.SECURITY_ROLES_MANAGE)


def test_auditor_reads_security_but_not_delivery(seeded, uow):
    ctx = _resolve(uow, "novabank-auditor-sub")
    assert ctx.has_permission(Permission.SECURITY_AUDIT_READ)
    assert not ctx.has_permission(Permission.CONNECTORS_SYNC)
    assert not ctx.has_permission(Permission.GRAPH_REBUILD)


def test_tenant_admin_can_manage_roles(seeded, uow):
    ctx = _resolve(uow, "novabank-admin-sub")
    assert ctx.has_permission(Permission.SECURITY_ROLES_MANAGE)
    assert ctx.has_permission(Permission.PREDICTIONS_PROMOTE)


def test_no_principal_can_access_another_tenant(seeded, uow):
    with pytest.raises(TenantSelectionError):
        _resolve(uow, "novabank-admin-sub", tenant="acmecorp")
