"""Delivery Prediction ORM models (Phase 3 Prompt 4).

Tenant-scoped persistence for outcomes, feature snapshots, datasets, models,
evaluations, prediction runs, predictions and factors.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class _PredictionTenantBase(Base):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class DeliveryOutcome(_PredictionTenantBase):
    __tablename__ = "ent_delivery_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "target_type",
            "target_id",
            "prediction_cutoff_at",
            "horizon_days",
            "label_version",
            name="uq_ent_delivery_outcomes_target_cutoff",
        ),
        Index(
            "ix_ent_do_tenant_target_cutoff_horizon",
            "tenant_id",
            "target_type",
            "target_id",
            "prediction_cutoff_at",
            "horizon_days",
        ),
        Index("ix_ent_do_tenant_verification", "tenant_id", "verification_status"),
        Index("ix_ent_do_tenant_category", "tenant_id", "outcome_category"),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_do_horizon_bounded",
        ),
        CheckConstraint(
            "binary_label IS NULL OR binary_label IN (0, 1)",
            name="ck_ent_do_binary_label",
        ),
        CheckConstraint(
            "observation_window_end_at >= prediction_cutoff_at",
            name="ck_ent_do_observation_window",
        ),
        CheckConstraint(
            "target_due_at >= prediction_cutoff_at",
            name="ck_ent_do_due_after_cutoff",
        ),
    )

    delivery_outcome_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_definition: Mapped[str] = mapped_column(String(64), nullable=False)
    label_version: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    prediction_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_window_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actual_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome_category: Mapped[str] = mapped_column(String(32), nullable=False)
    binary_label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_source: Mapped[str] = mapped_column(String(64), nullable=False)
    supporting_evidence_signal_ids: Mapped[list] = mapped_column(
        PortableJSON(), nullable=False, default=list
    )
    source_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    data_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class PredictionFeatureSnapshot(_PredictionTenantBase):
    __tablename__ = "ent_prediction_feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "target_type",
            "target_id",
            "as_of_at",
            "horizon_days",
            "feature_schema_version",
            name="uq_ent_pfs_target_asof",
        ),
        Index(
            "ix_ent_pfs_tenant_target_asof",
            "tenant_id",
            "target_type",
            "target_id",
            "as_of_at",
        ),
        Index(
            "ix_ent_pfs_tenant_schema",
            "tenant_id",
            "feature_schema_version",
        ),
        Index("ix_ent_pfs_tenant_hash", "tenant_id", "feature_hash"),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pfs_horizon_bounded",
        ),
        CheckConstraint(
            "evidence_cutoff_at <= as_of_at",
            name="ck_ent_pfs_evidence_cutoff",
        ),
    )

    prediction_feature_snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_values: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    missingness_indicators: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    feature_lineage: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    source_high_watermarks: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    graph_projection_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    graph_analysis_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    readiness_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_warnings: Mapped[list] = mapped_column(PortableJSON(), nullable=False)


class PredictionDatasetManifest(_PredictionTenantBase):
    __tablename__ = "ent_prediction_dataset_manifests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "dataset_hash",
            name="uq_ent_pdm_tenant_dataset_hash",
        ),
        Index("ix_ent_pdm_tenant_hash", "tenant_id", "dataset_hash"),
        Index("ix_ent_pdm_tenant_horizon", "tenant_id", "horizon_days"),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pdm_horizon_bounded",
        ),
        CheckConstraint("total_rows >= 0", name="ck_ent_pdm_total_rows"),
        CheckConstraint("labeled_rows >= 0", name="ck_ent_pdm_labeled_rows"),
        CheckConstraint("positive_rows >= 0", name="ck_ent_pdm_positive_rows"),
        CheckConstraint("negative_rows >= 0", name="ck_ent_pdm_negative_rows"),
        CheckConstraint("tenant_count = 1", name="ck_ent_pdm_single_tenant"),
    )

    prediction_dataset_manifest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_definition: Mapped[str] = mapped_column(String(64), nullable=False)
    label_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    minimum_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    maximum_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    labeled_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    censored_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False)
    split_strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    train_row_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_row_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    test_row_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    leakage_report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    source_high_watermarks: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    exclusion_reasons: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    sufficiency_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sufficiency_report: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    train_row_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    calibration_row_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    test_row_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)


class PredictionModel(_PredictionTenantBase):
    __tablename__ = "ent_prediction_models"
    __table_args__ = (
        Index(
            "ix_ent_pm_tenant_state_horizon",
            "tenant_id",
            "model_state",
            "horizon_days",
        ),
        Index(
            "ix_ent_pm_tenant_active_scope",
            "tenant_id",
            "target_definition",
            "horizon_days",
            "usage_scope",
            "model_state",
        ),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pm_horizon_bounded",
        ),
        CheckConstraint(
            "model_state IN ('candidate','validated','active','rejected','retired')",
            name="ck_ent_pm_model_state",
        ),
        CheckConstraint(
            "NOT (data_scope = 'synthetic' AND production_eligible = 1)",
            name="ck_ent_pm_synthetic_not_prod",
        ),
    )

    prediction_model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_definition: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    label_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_manifest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    training_code_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_payload: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    training_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_state: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    production_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PredictionModelEvaluation(_PredictionTenantBase):
    __tablename__ = "ent_prediction_model_evaluations"
    __table_args__ = (
        Index(
            "ix_ent_pme_tenant_model",
            "tenant_id",
            "prediction_model_id",
        ),
        Index("ix_ent_pme_tenant_split", "tenant_id", "evaluation_split"),
        CheckConstraint("row_count >= 0", name="ck_ent_pme_row_count"),
        CheckConstraint("positive_count >= 0", name="ck_ent_pme_positive_count"),
        CheckConstraint("negative_count >= 0", name="ck_ent_pme_negative_count"),
    )

    prediction_model_evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prediction_model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_manifest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_split: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False)
    brier_score: Mapped[float] = mapped_column(Float, nullable=False)
    log_loss: Mapped[float] = mapped_column(Float, nullable=False)
    roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_calibration_error: Mapped[float] = mapped_column(Float, nullable=False)
    calibration_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_intercept: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_brier_score: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_log_loss: Mapped[float] = mapped_column(Float, nullable=False)
    confusion_matrix: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    threshold_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reliability_bins: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    evaluation_warnings: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    passed_validation_gates: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics_statistically_reliable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class PredictionRun(_PredictionTenantBase):
    __tablename__ = "ent_prediction_runs"
    __table_args__ = (
        Index(
            "ix_ent_pr_tenant_target_created",
            "tenant_id",
            "target_type",
            "target_id",
            "created_at",
        ),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_pr_horizon_bounded",
        ),
    )

    prediction_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimate_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sanitized_error_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)


class DeliveryPrediction(_PredictionTenantBase):
    __tablename__ = "ent_delivery_predictions"
    __table_args__ = (
        Index(
            "ix_ent_dp_tenant_target_created",
            "tenant_id",
            "target_type",
            "target_id",
            "created_at",
        ),
        Index("ix_ent_dp_tenant_hash", "tenant_id", "prediction_hash"),
        Index("ix_ent_dp_tenant_run", "tenant_id", "prediction_run_id"),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_dp_horizon_bounded",
        ),
        CheckConstraint(
            "probability_of_delivery_success IS NULL OR "
            "(probability_of_delivery_success >= 0 AND probability_of_delivery_success <= 1)",
            name="ck_ent_dp_probability_bounds",
        ),
        CheckConstraint(
            "uncalibrated_risk_score IS NULL OR "
            "(uncalibrated_risk_score >= 0 AND uncalibrated_risk_score <= 100)",
            name="ck_ent_dp_risk_score_bounds",
        ),
        CheckConstraint(
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
    )

    delivery_prediction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prediction_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_prediction_runs.prediction_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    probability_of_delivery_success: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncalibrated_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_band: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    baseline_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reliability_status: Mapped[str] = mapped_column(String(32), nullable=False)
    applicability_status: Mapped[str] = mapped_column(String(32), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prediction_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_quality_warnings: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    explanation_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PredictionFactor(_PredictionTenantBase):
    __tablename__ = "ent_prediction_factors"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "delivery_prediction_id",
            "rank",
            name="uq_ent_pf_prediction_rank",
        ),
        Index("ix_ent_pf_tenant_prediction", "tenant_id", "delivery_prediction_id"),
        CheckConstraint("rank >= 1 AND rank <= 8", name="ck_ent_pf_rank_bound"),
    )

    prediction_factor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    delivery_prediction_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_delivery_predictions.delivery_prediction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_or_rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_label: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)
    feature_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    coefficient: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    was_imputed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_refs: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    lineage_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
