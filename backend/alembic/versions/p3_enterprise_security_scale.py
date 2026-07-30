"""enterprise security and scale

Revision ID: p3_enterprise_security_scale
Revises: p3_ai_chief_of_staff
Create Date: 2026-07-30 14:30:00.000000

Additive Phase 3 Prompt 7 migration:
- Tenant identity providers (Entra OIDC mappings; no private keys stored).
- Security principals (users / service principals).
- Append-only role assignments (temporal revocation, never overwritten).
- Append-only security audit events.
- PostgreSQL Row-Level Security (enabled + forced) on every tenant-qualified
  table from Prompts 1-7, plus the audit log. SQLite skips RLS DDL (RLS is
  PostgreSQL-specific; SQLite is not proof of RLS).
"""

from typing import Sequence, Union

import sqlalchemy as sa

import app.db.types
from alembic import op

# Registering the ORM metadata lets us derive the reviewed RLS table list.
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.security.rls import (
    audit_rls_policy_statements,
    rls_disable_statements,
    rls_policy_statements,
    tenant_rls_tables,
)

revision: str = "p3_enterprise_security_scale"
down_revision: Union[str, Sequence[str], None] = "p3_ai_chief_of_staff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    return op.get_context().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "ent_identity_providers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("external_tenant_id", sa.String(length=128), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("audience", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_type IN ('entra_oidc', 'local_development', 'test')",
            name="ck_ent_idp_provider_type",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_identity_providers")),
        sa.UniqueConstraint(
            "tenant_id", "external_tenant_id", name="uq_ent_idp_tenant_external"
        ),
        sa.UniqueConstraint(
            "tenant_id", "issuer", "audience", name="uq_ent_idp_tenant_issuer_aud"
        ),
    )
    op.create_index("ix_ent_idp_tenant_enabled", "ent_identity_providers", ["tenant_id", "enabled"])
    op.create_index(
        op.f("ix_ent_identity_providers_tenant_id"), "ent_identity_providers", ["tenant_id"]
    )

    op.create_table(
        "ent_security_principals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("external_subject_id", sa.String(length=255), nullable=False),
        sa.Column("external_application_id", sa.String(length=255), nullable=True),
        sa.Column("display_label", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "principal_type IN ('user', 'service_principal')",
            name="ck_ent_principal_type",
        ),
        sa.CheckConstraint("status IN ('active', 'deactivated')", name="ck_ent_principal_status"),
        sa.CheckConstraint(
            "deactivated_at IS NULL OR status = 'deactivated'",
            name="ck_ent_principal_deactivated",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_security_principals")),
        sa.UniqueConstraint(
            "tenant_id", "external_subject_id", name="uq_ent_principal_tenant_subject"
        ),
    )
    op.create_index(
        "ix_ent_principal_tenant_status", "ent_security_principals", ["tenant_id", "status"]
    )
    op.create_index(
        op.f("ix_ent_security_principals_tenant_id"), "ent_security_principals", ["tenant_id"]
    )

    op.create_table(
        "ent_role_assignments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=48), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by_principal_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('tenant_admin', 'executive_reader', 'engineering_leader', "
            "'intelligence_analyst', 'integration_operator', 'security_auditor')",
            name="ck_ent_role_assignment_role",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_ent_role_assignment_temporal",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["ent_security_principals.id"],
            name=op.f("fk_ent_role_assignments_principal_id_ent_security_principals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_role_assignments")),
    )
    op.create_index(
        "ix_ent_role_assignment_lookup",
        "ent_role_assignments",
        ["tenant_id", "principal_id", "valid_from"],
    )
    op.create_index(
        "ix_ent_role_assignment_tenant_role", "ent_role_assignments", ["tenant_id", "role"]
    )
    op.create_index(
        op.f("ix_ent_role_assignments_tenant_id"), "ent_role_assignments", ["tenant_id"]
    )

    op.create_table(
        "ent_security_audit_events",
        sa.Column("sequence_no", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("principal_id", sa.String(length=64), nullable=True),
        sa.Column("external_subject_hash", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id_hash", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("request_method", sa.String(length=16), nullable=True),
        sa.Column("request_path", sa.String(length=255), nullable=True),
        sa.Column("source_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("event_metadata", app.db.types.PortableJSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('allow', 'deny')", name="ck_ent_audit_decision"),
        sa.PrimaryKeyConstraint("sequence_no", name=op.f("pk_ent_security_audit_events")),
        sa.UniqueConstraint("id", name=op.f("uq_ent_security_audit_events_id")),
    )
    op.create_index(
        "ix_ent_audit_tenant_created_seq",
        "ent_security_audit_events",
        ["tenant_id", "created_at", "sequence_no"],
    )
    op.create_index(
        "ix_ent_audit_tenant_action", "ent_security_audit_events", ["tenant_id", "action"]
    )
    op.create_index(
        "ix_ent_audit_correlation", "ent_security_audit_events", ["correlation_id"]
    )
    op.create_index(
        op.f("ix_ent_security_audit_events_tenant_id"),
        "ent_security_audit_events",
        ["tenant_id"],
    )

    # PostgreSQL row-level security (defense in depth). SQLite is a no-op.
    if _is_postgres():
        for table in tenant_rls_tables(Base.metadata):
            for statement in rls_policy_statements(table):
                op.execute(statement)
        for statement in audit_rls_policy_statements():
            op.execute(statement)


def downgrade() -> None:
    if _is_postgres():
        for table in tenant_rls_tables(Base.metadata):
            for statement in rls_disable_statements(table):
                op.execute(statement)
        for statement in rls_disable_statements("ent_security_audit_events"):
            op.execute(statement)

    op.drop_index(
        op.f("ix_ent_security_audit_events_tenant_id"), table_name="ent_security_audit_events"
    )
    op.drop_index("ix_ent_audit_correlation", table_name="ent_security_audit_events")
    op.drop_index("ix_ent_audit_tenant_action", table_name="ent_security_audit_events")
    op.drop_index("ix_ent_audit_tenant_created_seq", table_name="ent_security_audit_events")
    op.drop_table("ent_security_audit_events")

    op.drop_index(op.f("ix_ent_role_assignments_tenant_id"), table_name="ent_role_assignments")
    op.drop_index("ix_ent_role_assignment_tenant_role", table_name="ent_role_assignments")
    op.drop_index("ix_ent_role_assignment_lookup", table_name="ent_role_assignments")
    op.drop_table("ent_role_assignments")

    op.drop_index(
        op.f("ix_ent_security_principals_tenant_id"), table_name="ent_security_principals"
    )
    op.drop_index("ix_ent_principal_tenant_status", table_name="ent_security_principals")
    op.drop_table("ent_security_principals")

    op.drop_index(
        op.f("ix_ent_identity_providers_tenant_id"), table_name="ent_identity_providers"
    )
    op.drop_index("ix_ent_idp_tenant_enabled", table_name="ent_identity_providers")
    op.drop_table("ent_identity_providers")
