"""Synthetic NovaBank security fixtures (Phase 3 Prompt 7).

Bounded, fictional principals and role assignments for demonstrating RBAC. No
real employee identities or email addresses are used; subjects are synthetic
opaque identifiers.
"""

from __future__ import annotations

from app.db.unit_of_work import UnitOfWork
from app.security.enums import PrincipalType, SecurityRole

# (synthetic_subject, principal_type, role)
_NOVABANK_PRINCIPALS: tuple[tuple[str, PrincipalType, SecurityRole | None], ...] = (
    ("novabank-admin-sub", PrincipalType.USER, SecurityRole.TENANT_ADMIN),
    ("novabank-exec-sub", PrincipalType.USER, SecurityRole.EXECUTIVE_READER),
    ("novabank-eng-lead-sub", PrincipalType.USER, SecurityRole.ENGINEERING_LEADER),
    ("novabank-analyst-sub", PrincipalType.USER, SecurityRole.INTELLIGENCE_ANALYST),
    ("novabank-operator-sub", PrincipalType.USER, SecurityRole.INTEGRATION_OPERATOR),
    ("novabank-auditor-sub", PrincipalType.USER, SecurityRole.SECURITY_AUDITOR),
    (
        "novabank-service-principal-sub",
        PrincipalType.SERVICE_PRINCIPAL,
        SecurityRole.INTEGRATION_OPERATOR,
    ),
)


def seed_novabank_security(uow: UnitOfWork, *, tenant_id: str = "novabank") -> dict[str, int]:
    """Idempotent-ish seed: creates principals and one role assignment each.

    Returns counts. Safe to call on a fresh tenant; re-running creates additional
    append-only assignments (role history is intentionally append-only).
    """
    created_principals = 0
    created_assignments = 0
    for subject, principal_type, role in _NOVABANK_PRINCIPALS:
        existing = uow.security_principals.find_by_subject(tenant_id, subject)
        if existing is None:
            principal = uow.security_principals.create(
                tenant_id,
                principal_type=principal_type.value,
                external_subject_id=subject,
                display_label=subject,
            )
            created_principals += 1
        else:
            principal = existing
        if role is not None:
            uow.role_assignments.assign(
                tenant_id,
                principal_id=principal.id,
                role=role.value,
                reason="novabank synthetic seed",
            )
            created_assignments += 1
    return {
        "principals": created_principals,
        "role_assignments": created_assignments,
    }
