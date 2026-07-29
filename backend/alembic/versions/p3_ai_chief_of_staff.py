"""ai chief of staff

Revision ID: p3_ai_chief_of_staff
Revises: p3_continuous_scenario_intelligence
Create Date: 2026-07-30 01:00:00.000000

Additive Phase 3 Prompt 6 migration:
- Chief of Staff evidence snapshots
- Chief of Staff runs
- Chief of Staff briefs / claims / citations
- Chief of Staff reviews (append-only)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = "p3_ai_chief_of_staff"
down_revision: Union[str, Sequence[str], None] = "p3_continuous_scenario_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ent_cos_evidence_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("evidence_schema_version", sa.String(length=64), nullable=False),
        sa.Column("package_hash", sa.String(length=64), nullable=False),
        sa.Column("package_json", app.db.types.PortableJSON(), nullable=False),
        sa.Column("truncation_flags", app.db.types.PortableJSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IS NULL OR horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_cos_snap_horizon",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name=op.f("pk_ent_cos_evidence_snapshots")),
        sa.UniqueConstraint(
            "tenant_id",
            "package_hash",
            name="uq_ent_cos_snap_tenant_hash",
        ),
    )
    op.create_index(
        "ix_ent_cos_snap_tenant_target_asof",
        "ent_cos_evidence_snapshots",
        ["tenant_id", "target_type", "target_id", "as_of_at"],
    )
    op.create_index(
        "ix_ent_cos_snap_tenant_hash",
        "ent_cos_evidence_snapshots",
        ["tenant_id", "package_hash"],
    )
    op.create_index(
        op.f("ix_ent_cos_evidence_snapshots_tenant_id"),
        "ent_cos_evidence_snapshots",
        ["tenant_id"],
    )

    op.create_table(
        "ent_cos_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("evidence_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("prior_brief_id", sa.String(length=64), nullable=True),
        sa.Column("requested_provider", sa.String(length=32), nullable=False),
        sa.Column("final_provider", sa.String(length=32), nullable=False),
        sa.Column("model_deployment_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_schema_version", sa.String(length=64), nullable=False),
        sa.Column("output_schema_version", sa.String(length=64), nullable=False),
        sa.Column("fallback_template_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_package_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("generation_state", sa.String(length=32), nullable=False),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("grounding_result", sa.String(length=32), nullable=True),
        sa.Column("citation_result", sa.String(length=32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_latency_ms", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IS NULL OR horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_cos_run_horizon",
        ),
        sa.CheckConstraint(
            "generation_state IN ('generated', 'fallback_generated', 'rejected', 'failed')",
            name="ck_ent_cos_run_state",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["ent_cos_evidence_snapshots.snapshot_id"],
            name=op.f("fk_ent_cos_runs_evidence_snapshot_id_ent_cos_evidence_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_ent_cos_runs")),
    )
    op.create_index(
        "ix_ent_cos_run_tenant_target_asof",
        "ent_cos_runs",
        ["tenant_id", "target_type", "target_id", "as_of_at"],
    )
    op.create_index(
        "ix_ent_cos_run_tenant_state_created",
        "ent_cos_runs",
        ["tenant_id", "generation_state", "created_at"],
    )
    op.create_index(
        "ix_ent_cos_run_tenant_intent",
        "ent_cos_runs",
        ["tenant_id", "intent"],
    )
    op.create_index(
        "ix_ent_cos_run_tenant_prior_brief",
        "ent_cos_runs",
        ["tenant_id", "prior_brief_id"],
    )
    op.create_index(op.f("ix_ent_cos_runs_tenant_id"), "ent_cos_runs", ["tenant_id"])

    op.create_table(
        "ent_cos_briefs",
        sa.Column("brief_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("brief_json", app.db.types.PortableJSON(), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("output_schema_version", sa.String(length=64), nullable=False),
        sa.Column("generation_state", sa.String(length=32), nullable=False),
        sa.Column("final_provider", sa.String(length=32), nullable=False),
        sa.Column("estimate_kind", sa.String(length=64), nullable=True),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IS NULL OR horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_cos_brief_horizon",
        ),
        sa.CheckConstraint(
            "generation_state IN ('generated', 'fallback_generated', 'rejected', 'failed')",
            name="ck_ent_cos_brief_state",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ent_cos_runs.run_id"],
            name=op.f("fk_ent_cos_briefs_run_id_ent_cos_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["ent_cos_evidence_snapshots.snapshot_id"],
            name=op.f("fk_ent_cos_briefs_evidence_snapshot_id_ent_cos_evidence_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("brief_id", name=op.f("pk_ent_cos_briefs")),
        sa.UniqueConstraint("tenant_id", "run_id", name="uq_ent_cos_brief_tenant_run"),
    )
    op.create_index(
        "ix_ent_cos_brief_tenant_target_asof",
        "ent_cos_briefs",
        ["tenant_id", "target_type", "target_id", "as_of_at"],
    )
    op.create_index(
        "ix_ent_cos_brief_tenant_created",
        "ent_cos_briefs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_ent_cos_brief_tenant_hash",
        "ent_cos_briefs",
        ["tenant_id", "output_hash"],
    )
    op.create_index(op.f("ix_ent_cos_briefs_tenant_id"), "ent_cos_briefs", ["tenant_id"])

    # NOTE: prior_brief_id is an application-enforced immutable reference (no FK)
    # to avoid circular run↔brief FK and SQLite ALTER CONSTRAINT limitations.

    op.create_table(
        "ent_cos_claims",
        # claim_id stores "{brief_id}:{logical_claim_id}" (brief UUID + logical ≤64).
        sa.Column("claim_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("brief_id", sa.String(length=64), nullable=False),
        sa.Column("claim_type", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("support_status", sa.String(length=32), nullable=False),
        sa.Column("authorship", sa.String(length=32), nullable=False),
        sa.Column("temporal_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("semantic_metadata", app.db.types.PortableJSON(), nullable=False),
        sa.Column("ordering_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordering_index >= 0", name="ck_ent_cos_claim_order"),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["ent_cos_briefs.brief_id"],
            name=op.f("fk_ent_cos_claims_brief_id_ent_cos_briefs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("claim_id", name=op.f("pk_ent_cos_claims")),
        sa.UniqueConstraint(
            "tenant_id",
            "brief_id",
            "ordering_index",
            name="uq_ent_cos_claim_brief_order",
        ),
    )
    op.create_index(
        "ix_ent_cos_claim_tenant_brief",
        "ent_cos_claims",
        ["tenant_id", "brief_id"],
    )
    op.create_index(op.f("ix_ent_cos_claims_tenant_id"), "ent_cos_claims", ["tenant_id"])

    op.create_table(
        "ent_cos_citations",
        sa.Column("citation_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("brief_id", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("ordering_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordering_index >= 0", name="ck_ent_cos_citation_order"),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["ent_cos_briefs.brief_id"],
            name=op.f("fk_ent_cos_citations_brief_id_ent_cos_briefs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["ent_cos_claims.claim_id"],
            name=op.f("fk_ent_cos_citations_claim_id_ent_cos_claims"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["ent_cos_evidence_snapshots.snapshot_id"],
            name=op.f("fk_ent_cos_citations_package_id_ent_cos_evidence_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("citation_id", name=op.f("pk_ent_cos_citations")),
        sa.UniqueConstraint(
            "tenant_id",
            "claim_id",
            "evidence_id",
            name="uq_ent_cos_citation_claim_evidence",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "claim_id",
            "ordering_index",
            name="uq_ent_cos_citation_claim_order",
        ),
    )
    op.create_index(
        "ix_ent_cos_citation_tenant_brief",
        "ent_cos_citations",
        ["tenant_id", "brief_id"],
    )
    op.create_index(op.f("ix_ent_cos_citations_tenant_id"), "ent_cos_citations", ["tenant_id"])

    op.create_table(
        "ent_cos_reviews",
        sa.Column("review_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("brief_id", sa.String(length=64), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False),
        sa.Column("reviewer_context", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_state IN ('accepted', 'needs_revision', 'rejected', 'needs_more_evidence')",
            name="ck_ent_cos_review_state",
        ),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["ent_cos_briefs.brief_id"],
            name=op.f("fk_ent_cos_reviews_brief_id_ent_cos_briefs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_id", name=op.f("pk_ent_cos_reviews")),
    )
    op.create_index(
        "ix_ent_cos_review_tenant_brief_created",
        "ent_cos_reviews",
        ["tenant_id", "brief_id", "created_at"],
    )
    op.create_index(op.f("ix_ent_cos_reviews_tenant_id"), "ent_cos_reviews", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ent_cos_reviews_tenant_id"), table_name="ent_cos_reviews")
    op.drop_index("ix_ent_cos_review_tenant_brief_created", table_name="ent_cos_reviews")
    op.drop_table("ent_cos_reviews")

    op.drop_index(op.f("ix_ent_cos_citations_tenant_id"), table_name="ent_cos_citations")
    op.drop_index("ix_ent_cos_citation_tenant_brief", table_name="ent_cos_citations")
    op.drop_table("ent_cos_citations")

    op.drop_index(op.f("ix_ent_cos_claims_tenant_id"), table_name="ent_cos_claims")
    op.drop_index("ix_ent_cos_claim_tenant_brief", table_name="ent_cos_claims")
    op.drop_table("ent_cos_claims")

    op.drop_index(op.f("ix_ent_cos_briefs_tenant_id"), table_name="ent_cos_briefs")
    op.drop_index("ix_ent_cos_brief_tenant_hash", table_name="ent_cos_briefs")
    op.drop_index("ix_ent_cos_brief_tenant_created", table_name="ent_cos_briefs")
    op.drop_index("ix_ent_cos_brief_tenant_target_asof", table_name="ent_cos_briefs")
    op.drop_table("ent_cos_briefs")

    op.drop_index(op.f("ix_ent_cos_runs_tenant_id"), table_name="ent_cos_runs")
    op.drop_index("ix_ent_cos_run_tenant_prior_brief", table_name="ent_cos_runs")
    op.drop_index("ix_ent_cos_run_tenant_intent", table_name="ent_cos_runs")
    op.drop_index("ix_ent_cos_run_tenant_state_created", table_name="ent_cos_runs")
    op.drop_index("ix_ent_cos_run_tenant_target_asof", table_name="ent_cos_runs")
    op.drop_table("ent_cos_runs")

    op.drop_index(op.f("ix_ent_cos_evidence_snapshots_tenant_id"), table_name="ent_cos_evidence_snapshots")
    op.drop_index("ix_ent_cos_snap_tenant_hash", table_name="ent_cos_evidence_snapshots")
    op.drop_index("ix_ent_cos_snap_tenant_target_asof", table_name="ent_cos_evidence_snapshots")
    op.drop_table("ent_cos_evidence_snapshots")
