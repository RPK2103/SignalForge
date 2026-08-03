"""Deny-by-default RBAC permission matrix (Phase 3 Prompt 7).

There is exactly ONE versioned permission matrix. Rules:
- unknown role -> no permissions;
- unknown permission -> denied;
- expired assignment / deactivated principal -> resolved to zero roles upstream;
- multiple roles combine deterministically (set union);
- no implicit inheritance outside this matrix;
- model promotion and security administration are highly restricted;
- there is intentionally NO employee-ranking / surveillance permission.
"""

from __future__ import annotations

from types import MappingProxyType

from app.security.enums import Permission, SecurityRole

PERMISSION_MATRIX_VERSION = "2026-07-31.1"


def _perms(*permissions: Permission) -> frozenset[Permission]:
    return frozenset(permissions)


# The single source of truth. Do NOT grant permissions anywhere else.
_ROLE_PERMISSIONS: dict[SecurityRole, frozenset[Permission]] = {
    SecurityRole.TENANT_ADMIN: _perms(
        Permission.ENTERPRISE_READ,
        Permission.ENTERPRISE_MANAGE,
        Permission.CONNECTORS_READ,
        Permission.CONNECTORS_SYNC,
        Permission.CONNECTORS_MANAGE,
        Permission.GRAPH_READ,
        Permission.GRAPH_REBUILD,
        Permission.PREDICTIONS_READ,
        Permission.PREDICTIONS_TRAIN,
        Permission.PREDICTIONS_VALIDATE,
        Permission.PREDICTIONS_PROMOTE,
        Permission.SCENARIOS_READ,
        Permission.SCENARIOS_RUN,
        Permission.SCENARIOS_MANAGE_WATCHES,
        Permission.CHIEF_OF_STAFF_READ,
        Permission.CHIEF_OF_STAFF_GENERATE,
        Permission.CHIEF_OF_STAFF_REVIEW,
        Permission.SECURITY_AUDIT_READ,
        Permission.SECURITY_ROLES_MANAGE,
        Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE,
        # Prompt 8: full observability + AI-quality control.
        Permission.OBSERVABILITY_READ,
        Permission.OBSERVABILITY_MANAGE,
        Permission.AI_QUALITY_READ,
        Permission.AI_QUALITY_EVALUATE,
    ),
    SecurityRole.EXECUTIVE_READER: _perms(
        Permission.ENTERPRISE_READ,
        Permission.GRAPH_READ,
        Permission.PREDICTIONS_READ,
        Permission.SCENARIOS_READ,
        Permission.CHIEF_OF_STAFF_READ,
    ),
    SecurityRole.ENGINEERING_LEADER: _perms(
        Permission.ENTERPRISE_READ,
        Permission.CONNECTORS_READ,
        Permission.GRAPH_READ,
        Permission.PREDICTIONS_READ,
        Permission.SCENARIOS_READ,
        Permission.SCENARIOS_RUN,
        Permission.CHIEF_OF_STAFF_READ,
    ),
    SecurityRole.INTELLIGENCE_ANALYST: _perms(
        Permission.ENTERPRISE_READ,
        Permission.GRAPH_READ,
        Permission.PREDICTIONS_READ,
        Permission.PREDICTIONS_VALIDATE,
        Permission.SCENARIOS_READ,
        Permission.CHIEF_OF_STAFF_READ,
        # Prompt 8: analysts read AI quality and can trigger offline evaluations.
        Permission.AI_QUALITY_READ,
        Permission.AI_QUALITY_EVALUATE,
    ),
    SecurityRole.INTEGRATION_OPERATOR: _perms(
        Permission.ENTERPRISE_READ,
        Permission.CONNECTORS_READ,
        Permission.CONNECTORS_SYNC,
        Permission.CONNECTORS_MANAGE,
        Permission.GRAPH_READ,
        Permission.GRAPH_REBUILD,
        # Prompt 8: operators monitor pipeline/connector health.
        Permission.OBSERVABILITY_READ,
    ),
    SecurityRole.SECURITY_AUDITOR: _perms(
        Permission.SECURITY_AUDIT_READ,
        Permission.ENTERPRISE_READ,
        # Prompt 8: auditors read observability + AI quality (no mutation).
        Permission.OBSERVABILITY_READ,
        Permission.AI_QUALITY_READ,
    ),
}

ROLE_PERMISSIONS: MappingProxyType[SecurityRole, frozenset[Permission]] = MappingProxyType(
    _ROLE_PERMISSIONS
)


def resolve_roles(role_values: object) -> frozenset[SecurityRole]:
    """Map raw role strings to known roles. Unknown roles are silently dropped
    (deny-by-default: they grant nothing)."""
    resolved: set[SecurityRole] = set()
    if not role_values:
        return frozenset()
    for raw in role_values:
        try:
            resolved.add(SecurityRole(str(raw)))
        except ValueError:
            continue
    return frozenset(resolved)


def permissions_for_roles(roles: frozenset[SecurityRole]) -> frozenset[Permission]:
    """Union the permissions of the given known roles."""
    effective: set[Permission] = set()
    for role in roles:
        effective.update(ROLE_PERMISSIONS.get(role, frozenset()))
    return frozenset(effective)


def matrix_snapshot() -> dict[str, list[str]]:
    """Serializable snapshot of the matrix (for docs / audit / tests)."""
    return {
        role.value: sorted(perm.value for perm in perms)
        for role, perms in _ROLE_PERMISSIONS.items()
    }
