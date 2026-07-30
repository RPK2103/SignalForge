"""RBAC matrix + deny-by-default resolution tests (Phase 3 Prompt 7)."""

from __future__ import annotations

from app.security.enums import Permission, SecurityRole
from app.security.permissions import (
    PERMISSION_MATRIX_VERSION,
    matrix_snapshot,
    permissions_for_roles,
    resolve_roles,
)


def test_matrix_is_versioned():
    assert PERMISSION_MATRIX_VERSION
    snapshot = matrix_snapshot()
    assert set(snapshot) == {role.value for role in SecurityRole}


def test_unknown_role_grants_nothing():
    roles = resolve_roles(["not_a_real_role"])
    assert roles == frozenset()
    assert permissions_for_roles(roles) == frozenset()


def test_empty_roles_grant_nothing():
    assert permissions_for_roles(frozenset()) == frozenset()


def test_role_union_is_deterministic():
    combined = permissions_for_roles(
        frozenset({SecurityRole.EXECUTIVE_READER, SecurityRole.INTEGRATION_OPERATOR})
    )
    # Union of both roles' permissions.
    assert Permission.ENTERPRISE_READ in combined
    assert Permission.CONNECTORS_SYNC in combined
    assert Permission.CHIEF_OF_STAFF_READ in combined
    # Neither role can promote a model.
    assert Permission.PREDICTIONS_PROMOTE not in combined


def test_model_promotion_is_restricted_to_tenant_admin():
    admins = permissions_for_roles(frozenset({SecurityRole.TENANT_ADMIN}))
    assert Permission.PREDICTIONS_PROMOTE in admins
    for role in SecurityRole:
        if role is SecurityRole.TENANT_ADMIN:
            continue
        perms = permissions_for_roles(frozenset({role}))
        assert Permission.PREDICTIONS_PROMOTE not in perms


def test_security_admin_is_restricted():
    for role in SecurityRole:
        perms = permissions_for_roles(frozenset({role}))
        if role is SecurityRole.TENANT_ADMIN:
            assert Permission.SECURITY_ROLES_MANAGE in perms
            assert Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE in perms
        else:
            assert Permission.SECURITY_ROLES_MANAGE not in perms
            assert Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE not in perms


def test_security_auditor_can_read_audit_only():
    perms = permissions_for_roles(frozenset({SecurityRole.SECURITY_AUDITOR}))
    assert Permission.SECURITY_AUDIT_READ in perms
    # Auditor cannot mutate delivery data.
    assert Permission.CHIEF_OF_STAFF_GENERATE not in perms
    assert Permission.CONNECTORS_SYNC not in perms
    assert Permission.GRAPH_REBUILD not in perms


def test_no_employee_ranking_permission_exists():
    values = {perm.value for perm in Permission}
    for banned in ("rank", "ranking", "surveillance", "performance"):
        assert not any(banned in value for value in values)
