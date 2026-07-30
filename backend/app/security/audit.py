"""Append-only security audit service (Phase 3 Prompt 7).

Persists denials, authentication failures and sensitive successful mutations.
Metadata is sanitized and hashed so no bearer token, raw header, or secret is
ever stored.

Audit-write failure policy: for security administration and model promotion the
mutation is fail-closed — a failed audit write raises and rolls back the
mutation. For lower-risk operations the audit write is best-effort and logged.
"""

from __future__ import annotations

import logging

from app.db.unit_of_work import UnitOfWork
from app.security.context import SecurityContext
from app.security.enums import (
    AuthenticationFailureCategory,
    AuthorizationDecision,
    Permission,
    SecurityAuditAction,
)
from app.security.models import AuditPage, SecurityAuditEventRecord
from app.security.redaction import hash_identifier, sanitize_metadata

_logger = logging.getLogger("app.security.audit")

# Permissions whose audit trail must be transactional (fail-closed).
_FAIL_CLOSED_PERMISSIONS = frozenset(
    {
        Permission.SECURITY_ROLES_MANAGE,
        Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE,
        Permission.PREDICTIONS_PROMOTE,
    }
)


class AuditWriteError(RuntimeError):
    """Raised when a fail-closed audit event could not be persisted."""


class SecurityAuditService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def commit(self) -> None:
        self._uow.commit()

    def rollback(self) -> None:
        self._uow.rollback()

    def record_authentication_failure(
        self,
        *,
        category: AuthenticationFailureCategory,
        correlation_id: str,
        request_method: str | None = None,
        request_path: str | None = None,
        external_subject: str | None = None,
        tenant_id: str | None = None,
        source_ip: str | None = None,
    ) -> SecurityAuditEventRecord:
        return self._uow.security_audit_events.append(
            action=SecurityAuditAction.AUTHENTICATION_FAILURE.value,
            resource_type="authentication",
            decision=AuthorizationDecision.DENY.value,
            reason_code=category.value,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            external_subject_hash=hash_identifier(external_subject),
            request_method=request_method,
            request_path=request_path,
            source_ip_hash=hash_identifier(source_ip),
            event_metadata={},
        )

    def record_authorization_denied(
        self,
        context: SecurityContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        reason_code: str = "missing_permission",
        request_method: str | None = None,
        request_path: str | None = None,
    ) -> SecurityAuditEventRecord:
        return self._uow.security_audit_events.append(
            action=action,
            resource_type=resource_type,
            decision=AuthorizationDecision.DENY.value,
            reason_code=reason_code,
            correlation_id=context.correlation_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            external_subject_hash=hash_identifier(context.subject),
            resource_id_hash=hash_identifier(resource_id),
            request_method=request_method,
            request_path=request_path,
            event_metadata={},
        )

    def record_sensitive_action(
        self,
        context: SecurityContext,
        *,
        action: SecurityAuditAction,
        permission: Permission,
        resource_type: str,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> SecurityAuditEventRecord | None:
        """Record a successful sensitive mutation.

        For fail-closed permissions any persistence failure raises
        :class:`AuditWriteError` so the caller can roll back the mutation.
        """
        safe_metadata = sanitize_metadata(metadata)
        try:
            return self._uow.security_audit_events.append(
                action=action.value,
                resource_type=resource_type,
                decision=AuthorizationDecision.ALLOW.value,
                reason_code="granted",
                correlation_id=context.correlation_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                external_subject_hash=hash_identifier(context.subject),
                resource_id_hash=hash_identifier(resource_id),
                event_metadata=safe_metadata,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised or logged intentionally
            if permission in _FAIL_CLOSED_PERMISSIONS:
                raise AuditWriteError(f"Fail-closed audit write failed for {action.value}") from exc
            _logger.warning("best-effort security audit write failed for %s", action.value)
            return None

    def read_history(
        self,
        context: SecurityContext,
        *,
        limit: int = 50,
        cursor: int | None = None,
        action: str | None = None,
    ) -> AuditPage:
        return self._uow.security_audit_events.page(
            context.tenant_id, limit=limit, cursor=cursor, action=action
        )
