"""Enterprise security ORM models (Phase 3 Prompt 7).

Identity providers, security principals, append-only role assignments, and an
append-only security audit log. All tenant-qualified tables carry ``tenant_id``
and receive PostgreSQL row-level security (see the p3_enterprise_security_scale
migration). The audit table allows a NULL tenant only for pre-tenant
authentication failures.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenantIdentityProvider(Base):
    __tablename__ = "ent_identity_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_tenant_id", name="uq_ent_idp_tenant_external"),
        UniqueConstraint("tenant_id", "issuer", "audience", name="uq_ent_idp_tenant_issuer_aud"),
        CheckConstraint(
            "provider_type IN ('entra_oidc', 'local_development', 'test')",
            name="ck_ent_idp_provider_type",
        ),
        Index("ix_ent_idp_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    audience: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class SecurityPrincipal(Base):
    __tablename__ = "ent_security_principals"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "external_subject_id",
            name="uq_ent_principal_tenant_subject",
        ),
        CheckConstraint(
            "principal_type IN ('user', 'service_principal')",
            name="ck_ent_principal_type",
        ),
        CheckConstraint(
            "status IN ('active', 'deactivated')",
            name="ck_ent_principal_status",
        ),
        CheckConstraint(
            "deactivated_at IS NULL OR status = 'deactivated'",
            name="ck_ent_principal_deactivated",
        ),
        Index("ix_ent_principal_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_application_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleAssignment(Base):
    __tablename__ = "ent_role_assignments"
    __table_args__ = (
        CheckConstraint(
            "role IN ('tenant_admin', 'executive_reader', 'engineering_leader', "
            "'intelligence_analyst', 'integration_operator', 'security_auditor')",
            name="ck_ent_role_assignment_role",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_ent_role_assignment_temporal",
        ),
        Index(
            "ix_ent_role_assignment_lookup",
            "tenant_id",
            "principal_id",
            "valid_from",
        ),
        Index("ix_ent_role_assignment_tenant_role", "tenant_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_security_principals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(48), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_principal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class SecurityAuditEvent(Base):
    __tablename__ = "ent_security_audit_events"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'deny')",
            name="ck_ent_audit_decision",
        ),
        Index(
            "ix_ent_audit_tenant_created_seq",
            "tenant_id",
            "created_at",
            "sequence_no",
        ),
        Index("ix_ent_audit_tenant_action", "tenant_id", "action"),
        Index("ix_ent_audit_correlation", "correlation_id"),
    )

    # A monotonic surrogate key gives a stable keyset-pagination ordering that is
    # independent of created_at collisions.
    sequence_no: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    principal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_subject_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    request_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(PortableJSON(), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
