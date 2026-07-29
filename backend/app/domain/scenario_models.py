"""Continuous Scenario Intelligence domain models (Phase 3 Prompt 5).

Immutable definitions/versions/runs/results. Overlays never mutate source
enterprise, graph, or prediction tables. Estimates preserve Prompt 4
estimate_kind semantics — fallback scores are not probabilities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.prediction_enums import EstimateKind, RiskBand
from app.domain.scenario_constants import (
    DEFAULT_HORIZON_DAYS,
    MAX_AFFECTED_NODE_IDS,
    MAX_APPLICABILITY_WARNINGS,
    MAX_ASSUMPTION_IDS,
    MAX_DATA_QUALITY_WARNINGS,
    MAX_DESCRIPTION_CHARS,
    MAX_EXPLANATION_CHARS,
    MAX_IMPACTS_PER_RESULT,
    MAX_NAME_CHARS,
    MAX_SUPPORTING_EDGE_IDS,
    MIN_WATCH_INTERVAL_MINUTES,
    SCENARIO_FEATURE_OVERLAY_VERSION,
    SCENARIO_SCHEMA_VERSION,
    SUPPORTED_HORIZONS,
)
from app.domain.scenario_enums import (
    ComparisonDimension,
    EstimateComparability,
    ImpactDirection,
    ImpactSeverity,
    ScenarioImpactConfidence,
    ScenarioImpactType,
    ScenarioKind,
    ScenarioLifecycleState,
    ScenarioRunMode,
    ScenarioRunState,
    ScenarioTargetType,
    ScenarioTriggerAction,
    ScenarioTriggerReason,
    ScenarioWatchLifecycle,
    ScenarioWatchMode,
    SimulationOrigin,
)


def validate_horizon(horizon_days: int) -> int:
    if horizon_days not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported horizon_days={horizon_days}; supported={sorted(SUPPORTED_HORIZONS)}"
        )
    return horizon_days


class TenantScopedScenario(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)


class ScenarioDefinition(TenantScopedScenario):
    scenario_definition_id: str
    name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_CHARS)
    target_type: ScenarioTargetType
    target_id: str
    scenario_kind: ScenarioKind
    lifecycle_state: ScenarioLifecycleState = ScenarioLifecycleState.ACTIVE
    current_version: int = Field(ge=0, default=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class ScenarioVersion(TenantScopedScenario):
    scenario_version_id: str
    scenario_definition_id: str
    version_number: int = Field(ge=1)
    scenario_schema_version: str = SCENARIO_SCHEMA_VERSION
    assumptions: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime
    effective_to: datetime | None = None
    created_by_context: str = "cli"
    specification_hash: str
    created_at: datetime | None = None


class ScenarioWatch(TenantScopedScenario):
    scenario_watch_id: str
    scenario_definition_id: str
    scenario_version_id: str
    target_type: ScenarioTargetType
    target_id: str
    watch_mode: ScenarioWatchMode = ScenarioWatchMode.ON_CHANGE
    lifecycle_state: ScenarioWatchLifecycle = ScenarioWatchLifecycle.ACTIVE
    minimum_interval_minutes: int = Field(ge=MIN_WATCH_INTERVAL_MINUTES, default=60)
    last_evaluated_at: datetime | None = None
    next_eligible_at: datetime | None = None
    last_source_fingerprint: str | None = None
    last_scenario_run_id: str | None = None
    last_result_hash: str | None = None
    consecutive_failures: int = Field(ge=0, default=0)
    lock_version: int = Field(ge=0, default=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScenarioTriggerEvent(TenantScopedScenario):
    scenario_trigger_event_id: str
    scenario_watch_id: str
    detected_at: datetime
    trigger_reason: ScenarioTriggerReason
    previous_fingerprint: str | None = None
    current_fingerprint: str | None = None
    changed_components: list[str] = Field(default_factory=list, max_length=32)
    action: ScenarioTriggerAction
    scenario_run_id: str | None = None
    sanitized_error_summary: str | None = Field(default=None, max_length=512)
    created_at: datetime | None = None


class ScenarioRun(TenantScopedScenario):
    scenario_run_id: str
    scenario_version_id: str
    scenario_definition_id: str
    target_type: ScenarioTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int = DEFAULT_HORIZON_DAYS
    run_mode: ScenarioRunMode = ScenarioRunMode.MANUAL
    source_fingerprint: str
    baseline_fingerprint: str
    scenario_fingerprint: str
    run_input_hash: str
    graph_projection_version: str | None = None
    prediction_model_id: str | None = None
    prediction_baseline_version: str | None = None
    state: ScenarioRunState = ScenarioRunState.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    nodes_examined: int = Field(ge=0, default=0)
    edges_examined: int = Field(ge=0, default=0)
    impacts_created: int = Field(ge=0, default=0)
    sanitized_error_summary: str | None = Field(default=None, max_length=512)
    result_hash: str | None = None
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)


class ScenarioFeatureOverlay(TenantScopedScenario):
    scenario_feature_overlay_id: str
    scenario_run_id: str
    baseline_feature_snapshot_id: str | None = None
    feature_schema_version: str
    overlay_schema_version: str = SCENARIO_FEATURE_OVERLAY_VERSION
    baseline_values_hash: str
    changed_feature_values: dict[str, float] = Field(default_factory=dict)
    simulated_feature_values: dict[str, float] = Field(default_factory=dict)
    feature_delta: dict[str, float] = Field(default_factory=dict)
    feature_lineage: list[dict[str, Any]] = Field(default_factory=list)
    simulation_origin: SimulationOrigin = SimulationOrigin.SCENARIO_SIMULATED
    training_eligible: bool = False
    overlay_hash: str
    created_at: datetime | None = None

    @model_validator(mode="after")
    def _enforce_training_ineligible(self) -> ScenarioFeatureOverlay:
        if self.training_eligible:
            raise ValueError("scenario feature overlays must have training_eligible=false")
        return self


class ScenarioResult(TenantScopedScenario):
    scenario_result_id: str
    scenario_run_id: str
    target_type: ScenarioTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int
    scenario_kind: ScenarioKind
    baseline_summary: dict[str, Any] = Field(default_factory=dict)
    simulated_summary: dict[str, Any] = Field(default_factory=dict)
    delta_summary: dict[str, Any] = Field(default_factory=dict)
    baseline_estimate_kind: EstimateKind
    simulated_estimate_kind: EstimateKind
    estimate_comparability: EstimateComparability
    baseline_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    simulated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    probability_delta: float | None = None
    baseline_risk_score: float | None = Field(default=None, ge=0.0, le=100.0)
    simulated_risk_score: float | None = Field(default=None, ge=0.0, le=100.0)
    risk_score_delta: float | None = None
    baseline_risk_band: RiskBand | None = None
    simulated_risk_band: RiskBand | None = None
    affected_project_count: int = Field(ge=0, default=0)
    affected_initiative_count: int = Field(ge=0, default=0)
    affected_critical_initiative_count: int = Field(ge=0, default=0)
    findings_added_count: int = Field(ge=0, default=0)
    findings_removed_count: int = Field(ge=0, default=0)
    findings_worsened_count: int = Field(ge=0, default=0)
    findings_improved_count: int = Field(ge=0, default=0)
    data_quality_warnings: list[str] = Field(
        default_factory=list, max_length=MAX_DATA_QUALITY_WARNINGS
    )
    applicability_warnings: list[str] = Field(
        default_factory=list, max_length=MAX_APPLICABILITY_WARNINGS
    )
    assumption_summary: dict[str, Any] = Field(default_factory=dict)
    result_hash: str
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)


class ScenarioImpact(TenantScopedScenario):
    scenario_impact_id: str
    scenario_run_id: str
    impact_type: ScenarioImpactType
    primary_node_id: str | None = None
    affected_node_ids: list[str] = Field(default_factory=list, max_length=MAX_AFFECTED_NODE_IDS)
    supporting_edge_ids: list[str] = Field(default_factory=list, max_length=MAX_SUPPORTING_EDGE_IDS)
    supporting_evidence_signal_ids: list[str] = Field(default_factory=list, max_length=16)
    assumption_ids: list[str] = Field(default_factory=list, max_length=MAX_ASSUMPTION_IDS)
    direction: ImpactDirection = ImpactDirection.NEUTRAL
    magnitude: float | None = None
    unit: str | None = Field(default=None, max_length=32)
    severity: ImpactSeverity = ImpactSeverity.MEDIUM
    confidence: ScenarioImpactConfidence = ScenarioImpactConfidence.MEDIUM
    explanation: str = Field(max_length=MAX_EXPLANATION_CHARS)
    impact_hash: str
    created_at: datetime | None = None


class ScenarioComparisonDimensionValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ComparisonDimension
    values_by_run_id: dict[str, float | int | None] = Field(default_factory=dict)


class ScenarioComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    target_type: ScenarioTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int
    estimate_comparability: EstimateComparability
    run_ids: list[str]
    dimensions: list[ScenarioComparisonDimensionValue]
    ordered_run_ids: list[str]
    sort_dimension: ComparisonDimension
    warnings: list[str] = Field(default_factory=list)
    comparable: bool = True


class ScenarioExecutionBundle(BaseModel):
    """Service return type for a completed (or reused) scenario run."""

    model_config = ConfigDict(extra="forbid")

    run: ScenarioRun
    result: ScenarioResult | None = None
    impacts: list[ScenarioImpact] = Field(default_factory=list, max_length=MAX_IMPACTS_PER_RESULT)
    feature_overlay: ScenarioFeatureOverlay | None = None
    reused_existing: bool = False


class ScenarioWatchEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watch: ScenarioWatch
    trigger: ScenarioTriggerEvent
    run: ScenarioRun | None = None
    result: ScenarioResult | None = None
    action: ScenarioTriggerAction


class ScenarioDueEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluated: int = 0
    skipped_no_change: int = 0
    skipped_interval: int = 0
    failed: int = 0
    results: list[ScenarioWatchEvaluationResult] = Field(default_factory=list)


class ScenarioHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    definition_count: int
    version_count: int
    run_count: int
    succeeded_run_count: int
    watch_count: int
    active_watch_count: int
    overlay_count: int
    training_eligible_overlay_count: int
    fallback_estimate_run_count: int
    calibrated_estimate_run_count: int
    schema_version: str = SCENARIO_SCHEMA_VERSION
    status: str = "ok"
