"""observability and ai quality

Revision ID: p3_observability_ai_quality
Revises: p3_enterprise_security_scale
Create Date: 2026-07-31 04:30:00.000000

Additive Phase 3 Prompt 8 migration:
- Bounded observability metric rollups.
- SLO definitions + append-only SLO evaluations.
- Internal alert events (fingerprint dedup + append-only transitions).
- AI-quality evaluation datasets, cases, runs and append-only results.
- Prediction quality (calibration/drift) snapshots.
- PostgreSQL Row-Level Security (enabled + forced) on every new tenant-qualified
  table. SQLite skips RLS DDL (RLS is PostgreSQL-specific).

No raw spans, logs, prompts, evidence packages or tokens are persisted here.
"""

from typing import Sequence, Union

import sqlalchemy as sa

import app.db.types
from alembic import op
from app.security.rls import rls_disable_statements, rls_policy_statements

revision: str = "p3_observability_ai_quality"
down_revision: Union[str, Sequence[str], None] = "p3_enterprise_security_scale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Only the NEW Prompt 8 tenant-qualified tables. Existing tables already have
# their RLS policies from prior migrations; we never re-apply to them here.
NEW_RLS_TABLES: tuple[str, ...] = (
    "ent_observability_metric_rollups",
    "ent_slo_definitions",
    "ent_slo_evaluations",
    "ent_alert_events",
    "ent_ai_evaluation_datasets",
    "ent_ai_evaluation_cases",
    "ent_ai_evaluation_runs",
    "ent_ai_evaluation_results",
    "ent_prediction_quality_snapshots",
)


def _is_postgres() -> bool:
    return op.get_context().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "ent_observability_metric_rollups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("dimensions", app.db.types.PortableJSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("service_version", sa.String(length=32), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_observability_metric_rollups")),
        sa.UniqueConstraint(
            "tenant_id",
            "metric_name",
            "window_start",
            "window_end",
            "canonical_hash",
            name="uq_ent_obs_rollup_window",
        ),
    )
    op.create_index(
        "ix_ent_obs_rollup_lookup",
        "ent_observability_metric_rollups",
        ["tenant_id", "metric_name", "window_start"],
    )
    op.create_index(
        op.f("ix_ent_observability_metric_rollups_tenant_id"),
        "ent_observability_metric_rollups",
        ["tenant_id"],
    )

    op.create_table(
        "ent_slo_definitions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("slo_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("indicator", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.Float(), nullable=False),
        sa.Column("comparison", sa.String(length=8), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("min_sample_count", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("comparison IN ('gte', 'lte')", name="ck_ent_slo_comparison"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_slo_definitions")),
        sa.UniqueConstraint("tenant_id", "slo_key", "version", name="uq_ent_slo_def_version"),
    )
    op.create_index("ix_ent_slo_def_lookup", "ent_slo_definitions", ["tenant_id", "slo_key"])
    op.create_index(
        op.f("ix_ent_slo_definitions_tenant_id"), "ent_slo_definitions", ["tenant_id"]
    )

    op.create_table(
        "ent_slo_evaluations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("slo_key", sa.String(length=64), nullable=False),
        sa.Column("slo_version", sa.Integer(), nullable=False),
        sa.Column("indicator", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("objective", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("event_metadata", app.db.types.PortableJSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('healthy', 'at_risk', 'breached', 'insufficient_data')",
            name="ck_ent_slo_eval_status",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_slo_evaluations")),
    )
    op.create_index(
        "ix_ent_slo_eval_lookup", "ent_slo_evaluations", ["tenant_id", "slo_key", "created_at"]
    )
    op.create_index(
        op.f("ix_ent_slo_evaluations_tenant_id"), "ent_slo_evaluations", ["tenant_id"]
    )

    op.create_table(
        "ent_alert_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("correlated_slo_key", sa.String(length=64), nullable=True),
        sa.Column("correlated_run_id", sa.String(length=64), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by_hash", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transitions", app.db.types.PortableJSON(), nullable=False),
        sa.Column("event_metadata", app.db.types.PortableJSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('open', 'acknowledged', 'resolved')", name="ck_ent_alert_state"
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_ent_alert_severity"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_alert_events")),
        sa.UniqueConstraint("tenant_id", "fingerprint", name="uq_ent_alert_fingerprint"),
    )
    op.create_index(
        "ix_ent_alert_lookup", "ent_alert_events", ["tenant_id", "state", "severity"]
    )
    op.create_index(op.f("ix_ent_alert_events_tenant_id"), "ent_alert_events", ["tenant_id"])

    op.create_table(
        "ent_ai_evaluation_datasets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("published", sa.Integer(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_ai_evaluation_datasets")),
        sa.UniqueConstraint(
            "tenant_id", "dataset_key", "version", name="uq_ent_ai_dataset_version"
        ),
    )
    op.create_index(
        "ix_ent_ai_dataset_lookup", "ent_ai_evaluation_datasets", ["tenant_id", "dataset_key"]
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_datasets_tenant_id"),
        "ent_ai_evaluation_datasets",
        ["tenant_id"],
    )

    op.create_table(
        "ent_ai_evaluation_cases",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("case_key", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("intent", sa.String(length=48), nullable=True),
        sa.Column("expected", app.db.types.PortableJSON(), nullable=False),
        sa.Column("payload", app.db.types.PortableJSON(), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("provider_version", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ent_ai_evaluation_datasets.id"],
            name=op.f("fk_ent_ai_evaluation_cases_dataset_id_ent_ai_evaluation_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_ai_evaluation_cases")),
        sa.UniqueConstraint("tenant_id", "dataset_id", "case_key", name="uq_ent_ai_case_key"),
    )
    op.create_index(
        "ix_ent_ai_case_lookup",
        "ent_ai_evaluation_cases",
        ["tenant_id", "dataset_id", "category"],
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_cases_dataset_id"),
        "ent_ai_evaluation_cases",
        ["dataset_id"],
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_cases_tenant_id"), "ent_ai_evaluation_cases", ["tenant_id"]
    )

    op.create_table(
        "ent_ai_evaluation_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=64), nullable=False),
        sa.Column("provider_variant", sa.String(length=48), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("aggregate_score", sa.Float(), nullable=True),
        sa.Column("release_gate_passed", sa.Integer(), nullable=True),
        sa.Column("critical_violations", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_metadata", app.db.types.PortableJSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'insufficient_data')",
            name="ck_ent_ai_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ent_ai_evaluation_datasets.id"],
            name=op.f("fk_ent_ai_evaluation_runs_dataset_id_ent_ai_evaluation_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_ai_evaluation_runs")),
    )
    op.create_index(
        "ix_ent_ai_run_lookup", "ent_ai_evaluation_runs", ["tenant_id", "created_at"]
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_runs_dataset_id"), "ent_ai_evaluation_runs", ["dataset_id"]
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_runs_tenant_id"), "ent_ai_evaluation_runs", ["tenant_id"]
    )

    op.create_table(
        "ent_ai_evaluation_results",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("case_key", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("detail", app.db.types.PortableJSON(), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'insufficient_data')",
            name="ck_ent_ai_result_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ent_ai_evaluation_runs.id"],
            name=op.f("fk_ent_ai_evaluation_results_run_id_ent_ai_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_ai_evaluation_results")),
    )
    op.create_index(
        "ix_ent_ai_result_lookup", "ent_ai_evaluation_results", ["tenant_id", "run_id"]
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_results_run_id"), "ent_ai_evaluation_results", ["run_id"]
    )
    op.create_index(
        op.f("ix_ent_ai_evaluation_results_tenant_id"),
        "ent_ai_evaluation_results",
        ["tenant_id"],
    )

    op.create_table(
        "ent_prediction_quality_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("snapshot_type", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("calibration_error", sa.Float(), nullable=True),
        sa.Column("drift_score", sa.Float(), nullable=True),
        sa.Column("drift_method", sa.String(length=24), nullable=True),
        sa.Column("label_coverage", sa.Float(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("distributions", app.db.types.PortableJSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('available', 'insufficient_data', 'unavailable')",
            name="ck_ent_pred_quality_status",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ent_prediction_quality_snapshots")),
    )
    op.create_index(
        "ix_ent_pred_quality_lookup",
        "ent_prediction_quality_snapshots",
        ["tenant_id", "model_version", "created_at"],
    )
    op.create_index(
        op.f("ix_ent_prediction_quality_snapshots_tenant_id"),
        "ent_prediction_quality_snapshots",
        ["tenant_id"],
    )

    # PostgreSQL row-level security (defense in depth) on the NEW tables only.
    if _is_postgres():
        for table in NEW_RLS_TABLES:
            for statement in rls_policy_statements(table):
                op.execute(statement)


def downgrade() -> None:
    if _is_postgres():
        for table in reversed(NEW_RLS_TABLES):
            for statement in rls_disable_statements(table):
                op.execute(statement)

    op.drop_index(
        op.f("ix_ent_prediction_quality_snapshots_tenant_id"),
        table_name="ent_prediction_quality_snapshots",
    )
    op.drop_index(
        "ix_ent_pred_quality_lookup", table_name="ent_prediction_quality_snapshots"
    )
    op.drop_table("ent_prediction_quality_snapshots")

    op.drop_index(
        op.f("ix_ent_ai_evaluation_results_tenant_id"), table_name="ent_ai_evaluation_results"
    )
    op.drop_index(
        op.f("ix_ent_ai_evaluation_results_run_id"), table_name="ent_ai_evaluation_results"
    )
    op.drop_index("ix_ent_ai_result_lookup", table_name="ent_ai_evaluation_results")
    op.drop_table("ent_ai_evaluation_results")

    op.drop_index(
        op.f("ix_ent_ai_evaluation_runs_tenant_id"), table_name="ent_ai_evaluation_runs"
    )
    op.drop_index(
        op.f("ix_ent_ai_evaluation_runs_dataset_id"), table_name="ent_ai_evaluation_runs"
    )
    op.drop_index("ix_ent_ai_run_lookup", table_name="ent_ai_evaluation_runs")
    op.drop_table("ent_ai_evaluation_runs")

    op.drop_index(
        op.f("ix_ent_ai_evaluation_cases_tenant_id"), table_name="ent_ai_evaluation_cases"
    )
    op.drop_index(
        op.f("ix_ent_ai_evaluation_cases_dataset_id"), table_name="ent_ai_evaluation_cases"
    )
    op.drop_index("ix_ent_ai_case_lookup", table_name="ent_ai_evaluation_cases")
    op.drop_table("ent_ai_evaluation_cases")

    op.drop_index(
        op.f("ix_ent_ai_evaluation_datasets_tenant_id"),
        table_name="ent_ai_evaluation_datasets",
    )
    op.drop_index("ix_ent_ai_dataset_lookup", table_name="ent_ai_evaluation_datasets")
    op.drop_table("ent_ai_evaluation_datasets")

    op.drop_index(op.f("ix_ent_alert_events_tenant_id"), table_name="ent_alert_events")
    op.drop_index("ix_ent_alert_lookup", table_name="ent_alert_events")
    op.drop_table("ent_alert_events")

    op.drop_index(op.f("ix_ent_slo_evaluations_tenant_id"), table_name="ent_slo_evaluations")
    op.drop_index("ix_ent_slo_eval_lookup", table_name="ent_slo_evaluations")
    op.drop_table("ent_slo_evaluations")

    op.drop_index(op.f("ix_ent_slo_definitions_tenant_id"), table_name="ent_slo_definitions")
    op.drop_index("ix_ent_slo_def_lookup", table_name="ent_slo_definitions")
    op.drop_table("ent_slo_definitions")

    op.drop_index(
        op.f("ix_ent_observability_metric_rollups_tenant_id"),
        table_name="ent_observability_metric_rollups",
    )
    op.drop_index(
        "ix_ent_obs_rollup_lookup", table_name="ent_observability_metric_rollups"
    )
    op.drop_table("ent_observability_metric_rollups")
