"""Observability & AI-quality ORM models (Phase 3 Prompt 8).

Only bounded operational rollups and quality records are persisted here — never
raw spans, logs, prompts, evidence packages or tokens (those belong to the
configured telemetry backend). Every table is tenant-qualified (NOT NULL
``tenant_id``) so it is automatically included in the forced-RLS registry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
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


class _ObsTenantBase(Base):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ObservabilityMetricRollup(_ObsTenantBase):
    """Bounded per-window metric rollup (per-tenant persistence; RLS protected)."""

    __tablename__ = "ent_observability_metric_rollups"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "metric_name",
            "window_start",
            "window_end",
            "canonical_hash",
            name="uq_ent_obs_rollup_window",
        ),
        Index("ix_ent_obs_rollup_lookup", "tenant_id", "metric_name", "window_start"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="count")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dimensions: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    service_version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.0.0")
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SloDefinition(_ObsTenantBase):
    __tablename__ = "ent_slo_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slo_key", "version", name="uq_ent_slo_def_version"),
        Index("ix_ent_slo_def_lookup", "tenant_id", "slo_key"),
        CheckConstraint("comparison IN ('gte', 'lte')", name="ck_ent_slo_comparison"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slo_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    indicator: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[float] = mapped_column(Float, nullable=False)
    comparison: Mapped[str] = mapped_column(String(8), nullable=False, default="gte")
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="ratio")
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    min_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")


class SloEvaluation(_ObsTenantBase):
    __tablename__ = "ent_slo_evaluations"
    __table_args__ = (
        Index("ix_ent_slo_eval_lookup", "tenant_id", "slo_key", "created_at"),
        CheckConstraint(
            "status IN ('healthy', 'at_risk', 'breached', 'insufficient_data')",
            name="ck_ent_slo_eval_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slo_key: Mapped[str] = mapped_column(String(64), nullable=False)
    slo_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    indicator: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluation_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    objective: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    event_metadata: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AlertEvent(_ObsTenantBase):
    __tablename__ = "ent_alert_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "fingerprint", name="uq_ent_alert_fingerprint"),
        Index("ix_ent_alert_lookup", "tenant_id", "state", "severity"),
        CheckConstraint("state IN ('open', 'acknowledged', 'resolved')", name="ck_ent_alert_state"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_ent_alert_severity"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    correlated_slo_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlated_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    acknowledged_by_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transitions: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    event_metadata: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")


class AiEvaluationDataset(_ObsTenantBase):
    __tablename__ = "ent_ai_evaluation_datasets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dataset_key", "version", name="uq_ent_ai_dataset_version"),
        Index("ix_ent_ai_dataset_lookup", "tenant_id", "dataset_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AiEvaluationCase(_ObsTenantBase):
    __tablename__ = "ent_ai_evaluation_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dataset_id", "case_key", name="uq_ent_ai_case_key"),
        Index("ix_ent_ai_case_lookup", "tenant_id", "dataset_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_ai_evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_key: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(48), nullable=True)
    expected: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AiEvaluationRun(_ObsTenantBase):
    __tablename__ = "ent_ai_evaluation_runs"
    __table_args__ = (
        Index("ix_ent_ai_run_lookup", "tenant_id", "created_at"),
        CheckConstraint(
            "status IN ('completed', 'failed', 'insufficient_data')",
            name="ck_ent_ai_run_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_ai_evaluation_datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    run_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_variant: Mapped[str] = mapped_column(String(48), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aggregate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_gate_passed: Mapped[bool | None] = mapped_column(Integer, nullable=True)
    critical_violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AiEvaluationResult(_ObsTenantBase):
    """Append-only per-case result rows for a run."""

    __tablename__ = "ent_ai_evaluation_results"
    __table_args__ = (
        Index("ix_ent_ai_result_lookup", "tenant_id", "run_id"),
        CheckConstraint(
            "status IN ('pass', 'fail', 'insufficient_data')",
            name="ck_ent_ai_result_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_ai_evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_key: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    passed: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    detail: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PredictionQualitySnapshot(_ObsTenantBase):
    __tablename__ = "ent_prediction_quality_snapshots"
    __table_args__ = (
        Index("ix_ent_pred_quality_lookup", "tenant_id", "model_version", "created_at"),
        CheckConstraint(
            "status IN ('available', 'insufficient_data', 'unavailable')",
            name="ck_ent_pred_quality_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False, default="calibration")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    brier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    label_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    distributions: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)
