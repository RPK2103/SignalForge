"""Tenant-scoped security repositories (Phase 3 Prompt 7).

Identity providers, principals, append-only role assignments, and an append-only
audit log with keyset pagination. Every read is qualified by ``tenant_id``; role
assignments are never overwritten (revocation stamps ``valid_to``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.security import (
    RoleAssignment,
    SecurityAuditEvent,
    SecurityPrincipal,
    TenantIdentityProvider,
)
from app.security.enums import SecurityRole
from app.security.models import (
    AuditPage,
    IdentityProviderRecord,
    RoleAssignmentRecord,
    SecurityAuditEventRecord,
    SecurityPrincipalRecord,
)

_MAX_AUDIT_PAGE = 100
_MAX_ROLE_HISTORY = 200


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdentityProviderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        tenant_id: str,
        *,
        provider_type: str,
        external_tenant_id: str,
        issuer: str,
        audience: str,
        enabled: bool = True,
    ) -> IdentityProviderRecord:
        existing = self._session.scalar(
            select(TenantIdentityProvider).where(
                TenantIdentityProvider.tenant_id == tenant_id,
                TenantIdentityProvider.external_tenant_id == external_tenant_id,
            )
        )
        now = _utcnow()
        if existing is None:
            row = TenantIdentityProvider(
                id=_new_id("idp"),
                tenant_id=tenant_id,
                provider_type=provider_type,
                external_tenant_id=external_tenant_id,
                issuer=issuer,
                audience=audience,
                enabled=1 if enabled else 0,
                configuration_version=1,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            existing.provider_type = provider_type
            existing.issuer = issuer
            existing.audience = audience
            existing.enabled = 1 if enabled else 0
            existing.configuration_version += 1
            existing.updated_at = now
            row = existing
        self._session.flush()
        return IdentityProviderRecord.model_validate(row)

    def list_for_tenant(self, tenant_id: str) -> list[IdentityProviderRecord]:
        rows = self._session.scalars(
            select(TenantIdentityProvider)
            .where(TenantIdentityProvider.tenant_id == tenant_id)
            .order_by(TenantIdentityProvider.created_at)
        ).all()
        return [IdentityProviderRecord.model_validate(row) for row in rows]

    def find_enabled(
        self, tenant_id: str, external_tenant_id: str
    ) -> IdentityProviderRecord | None:
        row = self._session.scalar(
            select(TenantIdentityProvider).where(
                TenantIdentityProvider.tenant_id == tenant_id,
                TenantIdentityProvider.external_tenant_id == external_tenant_id,
                TenantIdentityProvider.enabled == 1,
            )
        )
        return IdentityProviderRecord.model_validate(row) if row else None


class SecurityPrincipalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        tenant_id: str,
        *,
        principal_type: str,
        external_subject_id: str,
        external_application_id: str | None = None,
        display_label: str | None = None,
    ) -> SecurityPrincipalRecord:
        row = SecurityPrincipal(
            id=_new_id("prn"),
            tenant_id=tenant_id,
            principal_type=principal_type,
            external_subject_id=external_subject_id,
            external_application_id=external_application_id,
            display_label=display_label,
            status="active",
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return SecurityPrincipalRecord.model_validate(row)

    def _get_orm(self, tenant_id: str, external_subject_id: str) -> SecurityPrincipal | None:
        return self._session.scalar(
            select(SecurityPrincipal).where(
                SecurityPrincipal.tenant_id == tenant_id,
                SecurityPrincipal.external_subject_id == external_subject_id,
            )
        )

    def find_by_subject(
        self, tenant_id: str, external_subject_id: str
    ) -> SecurityPrincipalRecord | None:
        row = self._get_orm(tenant_id, external_subject_id)
        return SecurityPrincipalRecord.model_validate(row) if row else None

    def get(self, tenant_id: str, principal_id: str) -> SecurityPrincipalRecord | None:
        row = self._session.scalar(
            select(SecurityPrincipal).where(
                SecurityPrincipal.tenant_id == tenant_id,
                SecurityPrincipal.id == principal_id,
            )
        )
        return SecurityPrincipalRecord.model_validate(row) if row else None

    def deactivate(self, tenant_id: str, principal_id: str) -> SecurityPrincipalRecord | None:
        row = self._session.scalar(
            select(SecurityPrincipal).where(
                SecurityPrincipal.tenant_id == tenant_id,
                SecurityPrincipal.id == principal_id,
            )
        )
        if row is None:
            return None
        row.status = "deactivated"
        row.deactivated_at = _utcnow()
        self._session.flush()
        return SecurityPrincipalRecord.model_validate(row)


class RoleAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def assign(
        self,
        tenant_id: str,
        *,
        principal_id: str,
        role: str,
        assigned_by_principal_id: str | None = None,
        reason: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> RoleAssignmentRecord:
        row = RoleAssignment(
            id=_new_id("rol"),
            tenant_id=tenant_id,
            principal_id=principal_id,
            role=role,
            valid_from=valid_from or _utcnow(),
            valid_to=valid_to,
            assigned_by_principal_id=assigned_by_principal_id,
            reason=reason,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return RoleAssignmentRecord.model_validate(row)

    def revoke(
        self, tenant_id: str, *, assignment_id: str, revoked_at: datetime | None = None
    ) -> RoleAssignmentRecord | None:
        row = self._session.scalar(
            select(RoleAssignment).where(
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.id == assignment_id,
            )
        )
        if row is None:
            return None
        # Temporal revoke: never delete history, just bound its validity.
        row.valid_to = revoked_at or _utcnow()
        self._session.flush()
        return RoleAssignmentRecord.model_validate(row)

    def active_roles(
        self, tenant_id: str, principal_id: str, *, at: datetime | None = None
    ) -> frozenset[SecurityRole]:
        moment = at or _utcnow()
        rows = self._session.scalars(
            select(RoleAssignment).where(
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.principal_id == principal_id,
                RoleAssignment.valid_from <= moment,
            )
        ).all()
        roles: set[SecurityRole] = set()
        for row in rows:
            if row.valid_to is not None and _as_aware(row.valid_to) <= moment:
                continue
            try:
                roles.add(SecurityRole(row.role))
            except ValueError:
                continue
        return frozenset(roles)

    def history(
        self, tenant_id: str, principal_id: str, *, limit: int = 50
    ) -> list[RoleAssignmentRecord]:
        bounded = max(1, min(limit, _MAX_ROLE_HISTORY))
        rows = self._session.scalars(
            select(RoleAssignment)
            .where(
                RoleAssignment.tenant_id == tenant_id,
                RoleAssignment.principal_id == principal_id,
            )
            .order_by(RoleAssignment.created_at.desc(), RoleAssignment.id.desc())
            .limit(bounded)
        ).all()
        return [RoleAssignmentRecord.model_validate(row) for row in rows]


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class SecurityAuditEventRepository:
    """Append-only. No update/delete methods are exposed."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        action: str,
        resource_type: str,
        decision: str,
        reason_code: str,
        correlation_id: str,
        tenant_id: str | None = None,
        principal_id: str | None = None,
        external_subject_hash: str | None = None,
        resource_id_hash: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        source_ip_hash: str | None = None,
        event_metadata: dict | None = None,
    ) -> SecurityAuditEventRecord:
        row = SecurityAuditEvent(
            id=_new_id("aud"),
            tenant_id=tenant_id,
            principal_id=principal_id,
            external_subject_hash=external_subject_hash,
            action=action,
            resource_type=resource_type,
            resource_id_hash=resource_id_hash,
            decision=decision,
            reason_code=reason_code,
            correlation_id=correlation_id,
            request_method=request_method,
            request_path=request_path,
            source_ip_hash=source_ip_hash,
            event_metadata=event_metadata or {},
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return SecurityAuditEventRecord.model_validate(row)

    def page(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        cursor: int | None = None,
        action: str | None = None,
    ) -> AuditPage:
        """Keyset pagination over the monotonic ``sequence_no`` (descending)."""
        bounded = max(1, min(limit, _MAX_AUDIT_PAGE))
        query = select(SecurityAuditEvent).where(SecurityAuditEvent.tenant_id == tenant_id)
        if action is not None:
            query = query.where(SecurityAuditEvent.action == action)
        if cursor is not None:
            query = query.where(SecurityAuditEvent.sequence_no < cursor)
        query = query.order_by(SecurityAuditEvent.sequence_no.desc()).limit(bounded + 1)
        rows = self._session.scalars(query).all()
        has_more = len(rows) > bounded
        page_rows = rows[:bounded]
        next_cursor = page_rows[-1].sequence_no if has_more and page_rows else None
        return AuditPage(
            items=[SecurityAuditEventRecord.model_validate(row) for row in page_rows],
            next_cursor=next_cursor,
            limit=bounded,
        )
