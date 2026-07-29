"""Continuous Scenario Intelligence ORM models (Phase 3 Prompt 5).

Scenario overlays never mutate enterprise, graph, or prediction source tables.
training_eligible is constrained to false for feature overlays.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _ScenarioTenantBase(Base):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ScenarioDefinition(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_definitions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_ent_scen_def_tenant_name",
        ),
        Index("ix_ent_scen_def_tenant_target", "tenant_id", "target_type", "target_id"),
        Index("ix_ent_scen_def_tenant_kind", "tenant_id", "scenario_kind"),
        Index("ix_ent_scen_def_tenant_lifecycle", "tenant_id", "lifecycle_state"),
        CheckConstraint("current_version >= 0", name="ck_ent_scen_def_version_nonneg"),
    )

    scenario_definition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScenarioVersion(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scenario_definition_id",
            "version_number",
            name="uq_ent_scen_ver_def_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "specification_hash",
            name="uq_ent_scen_ver_spec_hash",
        ),
        Index("ix_ent_scen_ver_tenant_def", "tenant_id", "scenario_definition_id"),
        Index("ix_ent_scen_ver_tenant_hash", "tenant_id", "specification_hash"),
        CheckConstraint("version_number >= 1", name="ck_ent_scen_ver_number"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_ent_scen_ver_interval",
        ),
    )

    scenario_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_definition_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_definitions.scenario_definition_id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    assumptions: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_context: Mapped[str] = mapped_column(String(64), nullable=False, default="cli")
    specification_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ScenarioWatch(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_watches"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scenario_version_id",
            "target_type",
            "target_id",
            name="uq_ent_scen_watch_version_target",
        ),
        Index("ix_ent_scen_watch_tenant_lifecycle", "tenant_id", "lifecycle_state"),
        Index("ix_ent_scen_watch_tenant_next", "tenant_id", "next_eligible_at"),
        Index("ix_ent_scen_watch_tenant_fp", "tenant_id", "last_source_fingerprint"),
        CheckConstraint(
            "minimum_interval_minutes >= 60",
            name="ck_ent_scen_watch_interval",
        ),
        CheckConstraint("consecutive_failures >= 0", name="ck_ent_scen_watch_failures"),
        CheckConstraint("lock_version >= 0", name="ck_ent_scen_watch_lock"),
    )

    scenario_watch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_definition_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_definitions.scenario_definition_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scenario_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_versions.scenario_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    watch_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="on_change")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    minimum_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_eligible_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_source_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_scenario_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ScenarioTriggerEvent(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_trigger_events"
    __table_args__ = (
        Index("ix_ent_scen_trig_tenant_watch", "tenant_id", "scenario_watch_id"),
        Index("ix_ent_scen_trig_tenant_detected", "tenant_id", "detected_at"),
        Index("ix_ent_scen_trig_tenant_action", "tenant_id", "action"),
    )

    scenario_trigger_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_watch_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_watches.scenario_watch_id", ondelete="RESTRICT"),
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_components: Mapped[list] = mapped_column(PortableJSON(), nullable=False, default=list)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sanitized_error_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ScenarioRun(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "run_input_hash",
            name="uq_ent_scen_run_input_hash",
        ),
        Index("ix_ent_scen_run_tenant_version", "tenant_id", "scenario_version_id"),
        Index("ix_ent_scen_run_tenant_target", "tenant_id", "target_type", "target_id"),
        Index("ix_ent_scen_run_tenant_state", "tenant_id", "state"),
        Index("ix_ent_scen_run_tenant_asof", "tenant_id", "as_of_at"),
        Index("ix_ent_scen_run_tenant_fp", "tenant_id", "source_fingerprint"),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_scen_run_horizon",
        ),
        CheckConstraint("nodes_examined >= 0", name="ck_ent_scen_run_nodes"),
        CheckConstraint("edges_examined >= 0", name="ck_ent_scen_run_edges"),
        CheckConstraint("impacts_created >= 0", name="ck_ent_scen_run_impacts"),
    )

    scenario_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_versions.scenario_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scenario_definition_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_definitions.scenario_definition_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    run_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_projection_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prediction_model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prediction_baseline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nodes_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impacts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sanitized_error_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ScenarioFeatureOverlay(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_feature_overlays"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scenario_run_id",
            name="uq_ent_scen_overlay_run",
        ),
        Index("ix_ent_scen_overlay_tenant_run", "tenant_id", "scenario_run_id"),
        Index("ix_ent_scen_overlay_tenant_hash", "tenant_id", "overlay_hash"),
        CheckConstraint(
            "training_eligible = 0",
            name="ck_ent_scen_overlay_not_training",
        ),
    )

    scenario_feature_overlay_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_runs.scenario_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    baseline_feature_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    overlay_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_values_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_feature_values: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    simulated_feature_values: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    feature_delta: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    feature_lineage: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    simulation_origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="scenario_simulated"
    )
    training_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    overlay_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ScenarioResult(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_results"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scenario_run_id",
            name="uq_ent_scen_result_run",
        ),
        UniqueConstraint(
            "tenant_id",
            "result_hash",
            name="uq_ent_scen_result_hash",
        ),
        Index("ix_ent_scen_result_tenant_run", "tenant_id", "scenario_run_id"),
        Index("ix_ent_scen_result_tenant_target", "tenant_id", "target_type", "target_id"),
        CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_scen_result_horizon",
        ),
        CheckConstraint("affected_project_count >= 0", name="ck_ent_scen_result_proj"),
        CheckConstraint("affected_initiative_count >= 0", name="ck_ent_scen_result_init"),
        CheckConstraint("affected_critical_initiative_count >= 0", name="ck_ent_scen_result_crit"),
        CheckConstraint("findings_added_count >= 0", name="ck_ent_scen_result_fadd"),
        CheckConstraint("findings_removed_count >= 0", name="ck_ent_scen_result_frem"),
        CheckConstraint("findings_worsened_count >= 0", name="ck_ent_scen_result_fworse"),
        CheckConstraint("findings_improved_count >= 0", name="ck_ent_scen_result_fimp"),
        CheckConstraint(
            "baseline_probability IS NULL OR "
            "(baseline_probability >= 0 AND baseline_probability <= 1)",
            name="ck_ent_scen_result_bprob",
        ),
        CheckConstraint(
            "simulated_probability IS NULL OR "
            "(simulated_probability >= 0 AND simulated_probability <= 1)",
            name="ck_ent_scen_result_sprob",
        ),
        CheckConstraint(
            "baseline_risk_score IS NULL OR "
            "(baseline_risk_score >= 0 AND baseline_risk_score <= 100)",
            name="ck_ent_scen_result_bscore",
        ),
        CheckConstraint(
            "simulated_risk_score IS NULL OR "
            "(simulated_risk_score >= 0 AND simulated_risk_score <= 100)",
            name="ck_ent_scen_result_sscore",
        ),
    )

    scenario_result_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_runs.scenario_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_summary: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    simulated_summary: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    delta_summary: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    baseline_estimate_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    simulated_estimate_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    estimate_comparability: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_risk_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    simulated_risk_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    affected_project_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_initiative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_critical_initiative_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    findings_added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_removed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_worsened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_improved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_quality_warnings: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    applicability_warnings: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    assumption_summary: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ScenarioImpact(_ScenarioTenantBase):
    __tablename__ = "ent_scenario_impacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "impact_hash",
            name="uq_ent_scen_impact_hash",
        ),
        Index("ix_ent_scen_impact_tenant_run", "tenant_id", "scenario_run_id"),
        Index("ix_ent_scen_impact_tenant_type", "tenant_id", "impact_type"),
    )

    scenario_impact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_scenario_runs.scenario_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    impact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    affected_node_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    supporting_edge_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    supporting_evidence_signal_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    assumption_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(String(512), nullable=False)
    impact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
