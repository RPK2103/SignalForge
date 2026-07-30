"""delivery prediction foundation

Revision ID: p3_delivery_prediction
Revises: p3_delivery_graph
Create Date: 2026-07-29 01:00:00.000000

Additive Phase 3 Prompt 4 migration:
- DeliveryOutcome
- PredictionFeatureSnapshot
- PredictionDatasetManifest
- PredictionModel / PredictionModelEvaluation
- PredictionRun / DeliveryPrediction / PredictionFactor
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = "p3_delivery_prediction"
down_revision: Union[str, Sequence[str], None] = "p3_delivery_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ent_delivery_outcomes",
        sa.Column("delivery_outcome_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("outcome_definition", sa.String(length=64), nullable=False),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("prediction_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_category", sa.String(length=32), nullable=False),
        sa.Column("binary_label", sa.Integer(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("verification_source", sa.String(length=64), nullable=False),
        sa.Column(
            "supporting_evidence_signal_ids",
            app.db.types.PortableJSON(),
            nullable=False,
        ),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("notes_summary", sa.String(length=512), nullable=True),
        sa.Column("data_scope", sa.String(length=32), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_do_horizon_bounded",
        ),
        sa.CheckConstraint(
            "binary_label IS NULL OR binary_label IN (0, 1)",
            name="ck_ent_do_binary_label",
        ),
        sa.CheckConstraint(
            "observation_window_end_at >= prediction_cutoff_at",
            name="ck_ent_do_observation_window",
        ),
        sa.CheckConstraint(
            "target_due_at >= prediction_cutoff_at",
            name="ck_ent_do_due_after_cutoff",
        ),
        sa.PrimaryKeyConstraint("delivery_outcome_id", name=op.f("pk_ent_delivery_outcomes")),
        sa.UniqueConstraint(
            "tenant_id",
            "target_type",
            "target_id",
            "prediction_cutoff_at",
            "horizon_days",
            "label_version",
            name="uq_ent_delivery_outcomes_target_cutoff",
        ),
    )
    op.create_index(
        op.f("ix_ent_delivery_outcomes_tenant_id"),
        "ent_delivery_outcomes",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_do_tenant_target_cutoff_horizon",
        "ent_delivery_outcomes",
        ["tenant_id", "target_type", "target_id", "prediction_cutoff_at", "horizon_days"],
    )
    op.create_index(
        "ix_ent_do_tenant_verification",
        "ent_delivery_outcomes",
        ["tenant_id", "verification_status"],
    )
    op.create_index(
        "ix_ent_do_tenant_category",
        "ent_delivery_outcomes",
        ["tenant_id", "outcome_category"],
    )

    op.create_table(
        "ent_prediction_feature_snapshots",
        sa.Column("prediction_feature_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("feature_values", app.db.types.PortableJSON(), nullable=False),
        sa.Column("missingness_indicators", app.db.types.PortableJSON(), nullable=False),
        sa.Column("feature_lineage", app.db.types.PortableJSON(), nullable=False),
        sa.Column("source_high_watermarks", app.db.types.PortableJSON(), nullable=False),
        sa.Column("graph_projection_version", sa.String(length=16), nullable=True),
        sa.Column("graph_analysis_version", sa.String(length=16), nullable=True),
        sa.Column("evidence_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("readiness_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("feature_hash", sa.String(length=64), nullable=False),
        sa.Column("data_scope", sa.String(length=32), nullable=False),
        sa.Column("data_quality_warnings", app.db.types.PortableJSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pfs_horizon_bounded",
        ),
        sa.CheckConstraint(
            "evidence_cutoff_at <= as_of_at",
            name="ck_ent_pfs_evidence_cutoff",
        ),
        sa.PrimaryKeyConstraint(
            "prediction_feature_snapshot_id",
            name=op.f("pk_ent_prediction_feature_snapshots"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "target_type",
            "target_id",
            "as_of_at",
            "horizon_days",
            "feature_schema_version",
            name="uq_ent_pfs_target_asof",
        ),
    )
    op.create_index(
        op.f("ix_ent_prediction_feature_snapshots_tenant_id"),
        "ent_prediction_feature_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_pfs_tenant_target_asof",
        "ent_prediction_feature_snapshots",
        ["tenant_id", "target_type", "target_id", "as_of_at"],
    )
    op.create_index(
        "ix_ent_pfs_tenant_schema",
        "ent_prediction_feature_snapshots",
        ["tenant_id", "feature_schema_version"],
    )
    op.create_index(
        "ix_ent_pfs_tenant_hash",
        "ent_prediction_feature_snapshots",
        ["tenant_id", "feature_hash"],
    )

    op.create_table(
        "ent_prediction_dataset_manifests",
        sa.Column("prediction_dataset_manifest_id", sa.String(length=64), nullable=False),
        sa.Column("target_definition", sa.String(length=64), nullable=False),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minimum_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maximum_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("labeled_rows", sa.Integer(), nullable=False),
        sa.Column("excluded_rows", sa.Integer(), nullable=False),
        sa.Column("positive_rows", sa.Integer(), nullable=False),
        sa.Column("negative_rows", sa.Integer(), nullable=False),
        sa.Column("censored_rows", sa.Integer(), nullable=False),
        sa.Column("tenant_count", sa.Integer(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column("split_strategy", sa.String(length=64), nullable=False),
        sa.Column("train_row_ids_hash", sa.String(length=64), nullable=False),
        sa.Column("calibration_row_ids_hash", sa.String(length=64), nullable=False),
        sa.Column("test_row_ids_hash", sa.String(length=64), nullable=False),
        sa.Column("leakage_report_hash", sa.String(length=64), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("data_scope", sa.String(length=32), nullable=False),
        sa.Column("source_high_watermarks", app.db.types.PortableJSON(), nullable=False),
        sa.Column("exclusion_reasons", app.db.types.PortableJSON(), nullable=False),
        sa.Column("sufficiency_passed", sa.Boolean(), nullable=False),
        sa.Column("sufficiency_report", app.db.types.PortableJSON(), nullable=False),
        sa.Column("train_row_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("calibration_row_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("test_row_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pdm_horizon_bounded",
        ),
        sa.CheckConstraint("total_rows >= 0", name="ck_ent_pdm_total_rows"),
        sa.CheckConstraint("labeled_rows >= 0", name="ck_ent_pdm_labeled_rows"),
        sa.CheckConstraint("positive_rows >= 0", name="ck_ent_pdm_positive_rows"),
        sa.CheckConstraint("negative_rows >= 0", name="ck_ent_pdm_negative_rows"),
        sa.CheckConstraint("tenant_count = 1", name="ck_ent_pdm_single_tenant"),
        sa.PrimaryKeyConstraint(
            "prediction_dataset_manifest_id",
            name=op.f("pk_ent_prediction_dataset_manifests"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "dataset_hash",
            name="uq_ent_pdm_tenant_dataset_hash",
        ),
    )
    op.create_index(
        op.f("ix_ent_prediction_dataset_manifests_tenant_id"),
        "ent_prediction_dataset_manifests",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_pdm_tenant_hash",
        "ent_prediction_dataset_manifests",
        ["tenant_id", "dataset_hash"],
    )
    op.create_index(
        "ix_ent_pdm_tenant_horizon",
        "ent_prediction_dataset_manifests",
        ["tenant_id", "horizon_days"],
    )

    op.create_table(
        "ent_prediction_models",
        sa.Column("prediction_model_id", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_type", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("target_definition", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("dataset_manifest_id", sa.String(length=64), nullable=False),
        sa.Column("training_code_version", sa.String(length=64), nullable=False),
        sa.Column("parameter_payload", app.db.types.PortableJSON(), nullable=False),
        sa.Column("parameter_hash", sa.String(length=64), nullable=False),
        sa.Column("training_seed", sa.Integer(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_state", sa.String(length=32), nullable=False),
        sa.Column("usage_scope", sa.String(length=32), nullable=False),
        sa.Column("data_scope", sa.String(length=32), nullable=False),
        sa.Column("production_eligible", sa.Boolean(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pm_horizon_bounded",
        ),
        sa.CheckConstraint(
            "model_state IN ('candidate','validated','active','rejected','retired')",
            name="ck_ent_pm_model_state",
        ),
        sa.CheckConstraint(
            # Dialect-safe boolean predicate: comparing a Boolean column to the
            # integer 1 fails on PostgreSQL. A bare boolean column is portable.
            "NOT (data_scope = 'synthetic' AND production_eligible)",
            name="ck_ent_pm_synthetic_not_prod",
        ),
        sa.PrimaryKeyConstraint("prediction_model_id", name=op.f("pk_ent_prediction_models")),
    )
    op.create_index(
        op.f("ix_ent_prediction_models_tenant_id"),
        "ent_prediction_models",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_pm_tenant_state_horizon",
        "ent_prediction_models",
        ["tenant_id", "model_state", "horizon_days"],
    )
    op.create_index(
        "ix_ent_pm_tenant_active_scope",
        "ent_prediction_models",
        [
            "tenant_id",
            "target_definition",
            "horizon_days",
            "usage_scope",
            "model_state",
        ],
    )

    op.create_table(
        "ent_prediction_model_evaluations",
        sa.Column("prediction_model_evaluation_id", sa.String(length=64), nullable=False),
        sa.Column("prediction_model_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_manifest_id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_split", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False),
        sa.Column("negative_count", sa.Integer(), nullable=False),
        sa.Column("brier_score", sa.Float(), nullable=False),
        sa.Column("log_loss", sa.Float(), nullable=False),
        sa.Column("roc_auc", sa.Float(), nullable=True),
        sa.Column("average_precision", sa.Float(), nullable=True),
        sa.Column("expected_calibration_error", sa.Float(), nullable=False),
        sa.Column("calibration_slope", sa.Float(), nullable=True),
        sa.Column("calibration_intercept", sa.Float(), nullable=True),
        sa.Column("baseline_brier_score", sa.Float(), nullable=False),
        sa.Column("baseline_log_loss", sa.Float(), nullable=False),
        sa.Column("confusion_matrix", app.db.types.PortableJSON(), nullable=False),
        sa.Column("threshold_version", sa.String(length=32), nullable=False),
        sa.Column("reliability_bins", app.db.types.PortableJSON(), nullable=False),
        sa.Column("evaluation_warnings", app.db.types.PortableJSON(), nullable=False),
        sa.Column("passed_validation_gates", sa.Boolean(), nullable=False),
        sa.Column("metrics_statistically_reliable", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_count >= 0", name="ck_ent_pme_row_count"),
        sa.CheckConstraint("positive_count >= 0", name="ck_ent_pme_positive_count"),
        sa.CheckConstraint("negative_count >= 0", name="ck_ent_pme_negative_count"),
        sa.PrimaryKeyConstraint(
            "prediction_model_evaluation_id",
            name=op.f("pk_ent_prediction_model_evaluations"),
        ),
    )
    op.create_index(
        op.f("ix_ent_prediction_model_evaluations_tenant_id"),
        "ent_prediction_model_evaluations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_pme_tenant_model",
        "ent_prediction_model_evaluations",
        ["tenant_id", "prediction_model_id"],
    )
    op.create_index(
        "ix_ent_pme_tenant_split",
        "ent_prediction_model_evaluations",
        ["tenant_id", "evaluation_split"],
    )

    op.create_table(
        "ent_prediction_runs",
        sa.Column("prediction_run_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=True),
        sa.Column("feature_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimate_kind", sa.String(length=32), nullable=True),
        sa.Column("sanitized_error_summary", sa.String(length=256), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pr_horizon_bounded",
        ),
        sa.PrimaryKeyConstraint("prediction_run_id", name=op.f("pk_ent_prediction_runs")),
    )
    op.create_index(
        op.f("ix_ent_prediction_runs_tenant_id"),
        "ent_prediction_runs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_pr_tenant_target_created",
        "ent_prediction_runs",
        ["tenant_id", "target_type", "target_id", "created_at"],
    )

    op.create_table(
        "ent_delivery_predictions",
        sa.Column("delivery_prediction_id", sa.String(length=64), nullable=False),
        sa.Column("prediction_run_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("estimate_kind", sa.String(length=32), nullable=False),
        sa.Column("probability_of_delivery_success", sa.Float(), nullable=True),
        sa.Column("uncalibrated_risk_score", sa.Float(), nullable=True),
        sa.Column("risk_band", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=32), nullable=True),
        sa.Column("baseline_version", sa.String(length=32), nullable=True),
        sa.Column("reliability_status", sa.String(length=32), nullable=False),
        sa.Column("applicability_status", sa.String(length=32), nullable=False),
        sa.Column("data_scope", sa.String(length=32), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("prediction_hash", sa.String(length=64), nullable=False),
        sa.Column("data_quality_warnings", app.db.types.PortableJSON(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("explanation_summary", sa.String(length=512), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_dp_horizon_bounded",
        ),
        sa.CheckConstraint(
            "probability_of_delivery_success IS NULL OR "
            "(probability_of_delivery_success >= 0 AND probability_of_delivery_success <= 1)",
            name="ck_ent_dp_probability_bounds",
        ),
        sa.CheckConstraint(
            "uncalibrated_risk_score IS NULL OR "
            "(uncalibrated_risk_score >= 0 AND uncalibrated_risk_score <= 100)",
            name="ck_ent_dp_risk_score_bounds",
        ),
        sa.CheckConstraint(
            "("
            "estimate_kind = 'calibrated_probability' AND "
            "probability_of_delivery_success IS NOT NULL AND "
            "uncalibrated_risk_score IS NULL"
            ") OR ("
            "estimate_kind = 'uncalibrated_score' AND "
            "uncalibrated_risk_score IS NOT NULL AND "
            "probability_of_delivery_success IS NULL"
            ") OR ("
            "estimate_kind = 'insufficient_data' AND "
            "probability_of_delivery_success IS NULL AND "
            "uncalibrated_risk_score IS NULL"
            ")",
            name="ck_ent_dp_estimate_kind_fields",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_run_id"],
            ["ent_prediction_runs.prediction_run_id"],
            name=op.f("fk_ent_delivery_predictions_prediction_run_id_ent_prediction_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("delivery_prediction_id", name=op.f("pk_ent_delivery_predictions")),
    )
    op.create_index(
        op.f("ix_ent_delivery_predictions_tenant_id"),
        "ent_delivery_predictions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_dp_tenant_target_created",
        "ent_delivery_predictions",
        ["tenant_id", "target_type", "target_id", "created_at"],
    )
    op.create_index(
        "ix_ent_dp_tenant_hash",
        "ent_delivery_predictions",
        ["tenant_id", "prediction_hash"],
    )
    op.create_index(
        "ix_ent_dp_tenant_run",
        "ent_delivery_predictions",
        ["tenant_id", "prediction_run_id"],
    )

    op.create_table(
        "ent_prediction_factors",
        sa.Column("prediction_factor_id", sa.String(length=64), nullable=False),
        sa.Column("delivery_prediction_id", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("feature_or_rule_id", sa.String(length=64), nullable=False),
        sa.Column("feature_label", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=False),
        sa.Column("feature_value", sa.Float(), nullable=True),
        sa.Column("normalized_value", sa.Float(), nullable=True),
        sa.Column("coefficient", sa.Float(), nullable=True),
        sa.Column("rule_version", sa.String(length=32), nullable=True),
        sa.Column("was_imputed", sa.Boolean(), nullable=False),
        sa.Column("evidence_refs", app.db.types.PortableJSON(), nullable=False),
        sa.Column("lineage_summary", sa.String(length=256), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rank >= 1 AND rank <= 8", name="ck_ent_pf_rank_bound"),
        sa.ForeignKeyConstraint(
            ["delivery_prediction_id"],
            ["ent_delivery_predictions.delivery_prediction_id"],
            name=op.f("fk_ent_prediction_factors_delivery_prediction_id_ent_delivery_predictions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("prediction_factor_id", name=op.f("pk_ent_prediction_factors")),
        sa.UniqueConstraint(
            "tenant_id",
            "delivery_prediction_id",
            "rank",
            name="uq_ent_pf_prediction_rank",
        ),
    )
    op.create_index(
        op.f("ix_ent_prediction_factors_tenant_id"),
        "ent_prediction_factors",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_pf_tenant_prediction",
        "ent_prediction_factors",
        ["tenant_id", "delivery_prediction_id"],
    )


def downgrade() -> None:
    op.drop_table("ent_prediction_factors")
    op.drop_table("ent_delivery_predictions")
    op.drop_table("ent_prediction_runs")
    op.drop_table("ent_prediction_model_evaluations")
    op.drop_table("ent_prediction_models")
    op.drop_table("ent_prediction_dataset_manifests")
    op.drop_table("ent_prediction_feature_snapshots")
    op.drop_table("ent_delivery_outcomes")
