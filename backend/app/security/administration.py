"""Security administration service (Phase 3 Prompt 7).

Role assignment, identity-provider configuration, and principal lifecycle. Every
operation is authorized at the SERVICE layer (not only in API decorators) and is
audited. Security administration is fail-closed: a failed audit write rolls back
the mutation.
"""

from __future__ import annotations

from app.db.unit_of_work import UnitOfWork
from app.security.audit import AuditWriteError, SecurityAuditService
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import (
    Permission,
    PrincipalType,
    SecurityAuditAction,
    SecurityRole,
)
from app.security.exceptions import AuthorizationError, SecurityError
from app.security.models import (
    AuditPage,
    IdentityProviderRecord,
    RoleAssignmentRecord,
    SecurityPrincipalRecord,
)
from app.security.redaction import contains_secret


class SecurityAdministrationService:
    def __init__(
        self,
        uow: UnitOfWork,
        authz: AuthorizationService | None = None,
    ) -> None:
        self._uow = uow
        self._authz = authz or AuthorizationService()
        self._audit = SecurityAuditService(uow)

    # -- principals ---------------------------------------------------------
    def create_principal(
        self,
        context: SecurityContext,
        *,
        principal_type: PrincipalType,
        external_subject_id: str,
        external_application_id: str | None = None,
        display_label: str | None = None,
    ) -> SecurityPrincipalRecord:
        self._authz.require(context, Permission.SECURITY_ROLES_MANAGE, context.tenant_id)
        record = self._uow.security_principals.create(
            context.tenant_id,
            principal_type=principal_type.value,
            external_subject_id=external_subject_id,
            external_application_id=external_application_id,
            display_label=display_label,
        )
        self._uow.commit()
        return record

    def deactivate_principal(
        self, context: SecurityContext, *, principal_id: str
    ) -> SecurityPrincipalRecord:
        self._authz.require(context, Permission.SECURITY_ROLES_MANAGE, context.tenant_id)
        record = self._uow.security_principals.deactivate(context.tenant_id, principal_id)
        if record is None:
            raise SecurityError("Principal not found")
        self._uow.commit()
        return record

    # -- role assignments ---------------------------------------------------
    def assign_role(
        self,
        context: SecurityContext,
        *,
        principal_id: str,
        role: SecurityRole,
        reason: str | None = None,
    ) -> RoleAssignmentRecord:
        self._authz.require(context, Permission.SECURITY_ROLES_MANAGE, context.tenant_id)
        target = self._uow.security_principals.get(context.tenant_id, principal_id)
        if target is None:
            raise SecurityError("Principal not found")
        record = self._uow.role_assignments.assign(
            context.tenant_id,
            principal_id=principal_id,
            role=role.value,
            assigned_by_principal_id=context.principal_id,
            reason=reason,
        )
        self._audit_fail_closed(
            context,
            action=SecurityAuditAction.ROLE_ASSIGNMENT_CREATED,
            permission=Permission.SECURITY_ROLES_MANAGE,
            resource_type="role_assignment",
            resource_id=record.id,
            metadata={"role": role.value, "principal_id": principal_id},
        )
        return record

    def revoke_role(self, context: SecurityContext, *, assignment_id: str) -> RoleAssignmentRecord:
        self._authz.require(context, Permission.SECURITY_ROLES_MANAGE, context.tenant_id)
        record = self._uow.role_assignments.revoke(context.tenant_id, assignment_id=assignment_id)
        if record is None:
            raise SecurityError("Role assignment not found")
        self._audit_fail_closed(
            context,
            action=SecurityAuditAction.ROLE_ASSIGNMENT_REVOKED,
            permission=Permission.SECURITY_ROLES_MANAGE,
            resource_type="role_assignment",
            resource_id=record.id,
            metadata={"role": record.role, "principal_id": record.principal_id},
        )
        return record

    def list_role_history(
        self, context: SecurityContext, *, principal_id: str, limit: int = 50
    ) -> list[RoleAssignmentRecord]:
        self._authz.require(context, Permission.SECURITY_ROLES_MANAGE, context.tenant_id)
        return self._uow.role_assignments.history(context.tenant_id, principal_id, limit=limit)

    # -- identity providers -------------------------------------------------
    def upsert_identity_provider(
        self,
        context: SecurityContext,
        *,
        provider_type: str,
        external_tenant_id: str,
        issuer: str,
        audience: str,
        enabled: bool = True,
        metadata: dict | None = None,
    ) -> IdentityProviderRecord:
        self._authz.require(
            context, Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE, context.tenant_id
        )
        # Never accept private signing keys / secrets in identity-provider config.
        if metadata is not None and contains_secret(metadata):
            raise AuthorizationError(
                "Identity provider configuration must not contain secrets",
                reason_code="secret_rejected",
            )
        record = self._uow.identity_providers.upsert(
            context.tenant_id,
            provider_type=provider_type,
            external_tenant_id=external_tenant_id,
            issuer=issuer,
            audience=audience,
            enabled=enabled,
        )
        self._audit_fail_closed(
            context,
            action=SecurityAuditAction.IDENTITY_PROVIDER_CHANGED,
            permission=Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE,
            resource_type="identity_provider",
            resource_id=record.id,
            metadata={"provider_type": provider_type, "external_tenant_id": external_tenant_id},
        )
        return record

    def list_identity_providers(self, context: SecurityContext) -> list[IdentityProviderRecord]:
        self._authz.require(
            context, Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE, context.tenant_id
        )
        return self._uow.identity_providers.list_for_tenant(context.tenant_id)

    # -- audit read ---------------------------------------------------------
    def read_audit(
        self,
        context: SecurityContext,
        *,
        limit: int = 50,
        cursor: int | None = None,
        action: str | None = None,
    ) -> AuditPage:
        self._authz.require(context, Permission.SECURITY_AUDIT_READ, context.tenant_id)
        return self._uow.security_audit_events.page(
            context.tenant_id, limit=limit, cursor=cursor, action=action
        )

    # -- internal -----------------------------------------------------------
    def _audit_fail_closed(
        self,
        context: SecurityContext,
        *,
        action: SecurityAuditAction,
        permission: Permission,
        resource_type: str,
        resource_id: str | None,
        metadata: dict | None,
    ) -> None:
        try:
            self._audit.record_sensitive_action(
                context,
                action=action,
                permission=permission,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata,
            )
            self._uow.commit()
        except AuditWriteError:
            self._uow.rollback()
            raise
