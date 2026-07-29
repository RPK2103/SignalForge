"""Delivery Prediction domain DTOs (Phase 3 Prompt 4).

Pydantic models only — no ORM leakage. Predictions target project/initiative
delivery outcomes. Employee-performance prediction is not represented.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.prediction_constants import (
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    FORBIDDEN_FEATURE_TOKENS,
    LABEL_VERSION,
    MAX_DATA_QUALITY_WARNINGS,
    MAX_EVIDENCE_REFS,
    MAX_FACTORS,
    MAX_FEATURE_SNAPSHOT_BYTES,
    MAX_NOTES_SUMMARY,
    SUPPORTED_HORIZONS,
    TARGET_DEFINITION,
)
from app.domain.prediction_enums import (
    ApplicabilityStatus,
    EstimateKind,
    EvaluationSplit,
    FactorSourceKind,
    ModelState,
    ModelUsageScope,
    OutcomeCategory,
    PredictionDataScope,
    PredictionRunState,
    PredictionTargetType,
    ReliabilityStatus,
    RiskBand,
    VerificationStatus,
)


class PredictionTenantScoped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=2, max_length=64)


def validate_horizon(horizon_days: int) -> int:
    if horizon_days not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported horizon_days={horizon_days}; allowed={sorted(SUPPORTED_HORIZONS)}"
        )
    return horizon_days


def _reject_forbidden_keys(payload: dict[str, Any], *, context: str) -> None:
    for key in payload:
        lowered = key.lower()
        for token in FORBIDDEN_FEATURE_TOKENS:
            if token in lowered:
                raise ValueError(f"Forbidden key '{key}' in {context}")


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    if value != value or value in (float("inf"), float("-inf")):  # noqa: PLR0124
        raise ValueError("Non-finite numeric value is not allowed")
    return value


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------
class DeliveryOutcome(PredictionTenantScoped):
    delivery_outcome_id: str
    target_type: PredictionTargetType
    target_id: str
    outcome_definition: str = TARGET_DEFINITION
    label_version: str = LABEL_VERSION
    horizon_days: int = DEFAULT_HORIZON_DAYS
    prediction_cutoff_at: datetime
    target_due_at: datetime
    observation_window_end_at: datetime
    actual_completed_at: datetime | None = None
    outcome_category: OutcomeCategory
    binary_label: int | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verification_source: str = Field(default="manual", max_length=64)
    supporting_evidence_signal_ids: list[str] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_REFS
    )
    source_snapshot_id: str | None = Field(default=None, max_length=64)
    notes_summary: str | None = Field(default=None, max_length=MAX_NOTES_SUMMARY)
    data_scope: PredictionDataScope = PredictionDataScope.SYNTHETIC
    finalized_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)

    @field_validator("binary_label")
    @classmethod
    def _label(cls, value: int | None) -> int | None:
        if value is not None and value not in (0, 1):
            raise ValueError("binary_label must be 0, 1, or null")
        return value

    @model_validator(mode="after")
    def _consistency(self) -> DeliveryOutcome:
        if self.observation_window_end_at < self.prediction_cutoff_at:
            raise ValueError("observation_window_end_at must be >= prediction_cutoff_at")
        if self.target_due_at < self.prediction_cutoff_at:
            raise ValueError("target_due_at must be >= prediction_cutoff_at")
        unlabeled = {
            OutcomeCategory.UNKNOWN,
            OutcomeCategory.CENSORED,
        }
        if self.outcome_category in unlabeled and self.binary_label is not None:
            raise ValueError("unknown/censored outcomes must remain unlabeled")
        if (
            self.outcome_category not in unlabeled
            and self.verification_status == VerificationStatus.VERIFIED
            and self.binary_label is None
            and self.finalized_at is not None
        ):
            raise ValueError("finalized verified outcomes require a binary_label")
        if (
            self.actual_completed_at is not None
            and self.actual_completed_at < self.prediction_cutoff_at
        ):
            raise ValueError("actual_completed_at cannot precede prediction_cutoff_at")
        return self


# ---------------------------------------------------------------------------
# Feature snapshots
# ---------------------------------------------------------------------------
class FeatureLineageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(min_length=1, max_length=64)
    source_entity_type: str = Field(min_length=1, max_length=64)
    source_entity_id: str = Field(min_length=1, max_length=64)
    source_timestamp: datetime | None = None
    transformation_rule: str = Field(min_length=1, max_length=128)
    transformation_version: str = Field(min_length=1, max_length=32)


class PredictionFeatureSnapshot(PredictionTenantScoped):
    prediction_feature_snapshot_id: str
    target_type: PredictionTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int = DEFAULT_HORIZON_DAYS
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    feature_values: dict[str, float | None] = Field(default_factory=dict)
    missingness_indicators: dict[str, int] = Field(default_factory=dict)
    feature_lineage: list[FeatureLineageEntry] = Field(default_factory=list, max_length=64)
    source_high_watermarks: dict[str, str] = Field(default_factory=dict)
    graph_projection_version: str | None = Field(default=None, max_length=16)
    graph_analysis_version: str | None = Field(default=None, max_length=16)
    evidence_cutoff_at: datetime
    readiness_snapshot_id: str | None = Field(default=None, max_length=64)
    feature_hash: str = Field(min_length=64, max_length=64)
    data_scope: PredictionDataScope = PredictionDataScope.SYNTHETIC
    data_quality_warnings: list[str] = Field(
        default_factory=list, max_length=MAX_DATA_QUALITY_WARNINGS
    )
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)

    @model_validator(mode="after")
    def _validate_features(self) -> PredictionFeatureSnapshot:
        _reject_forbidden_keys(self.feature_values, context="feature_values")
        for name, value in self.feature_values.items():
            if value is not None:
                _finite_or_none(float(value))
            if name in {
                "binary_label",
                "outcome_category",
                "actual_completed_at",
                "probability_of_delivery_success",
            }:
                raise ValueError(f"Target leakage field '{name}' forbidden in features")
        if self.evidence_cutoff_at > self.as_of_at:
            raise ValueError("evidence_cutoff_at must be <= as_of_at")
        # Approximate payload bound via JSON length of values.
        approx = sum(len(k) + 16 for k in self.feature_values)
        if approx > MAX_FEATURE_SNAPSHOT_BYTES:
            raise ValueError("feature_values payload exceeds bound")
        return self


# ---------------------------------------------------------------------------
# Dataset manifests
# ---------------------------------------------------------------------------
class PredictionDatasetManifest(PredictionTenantScoped):
    prediction_dataset_manifest_id: str
    target_definition: str = TARGET_DEFINITION
    label_version: str = LABEL_VERSION
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    horizon_days: int = DEFAULT_HORIZON_DAYS
    generated_at: datetime
    minimum_cutoff_at: datetime
    maximum_cutoff_at: datetime
    total_rows: int = Field(ge=0)
    labeled_rows: int = Field(ge=0)
    excluded_rows: int = Field(ge=0)
    positive_rows: int = Field(ge=0)
    negative_rows: int = Field(ge=0)
    censored_rows: int = Field(ge=0)
    tenant_count: int = Field(ge=1, le=1)  # Prompt 4: single-tenant only
    feature_count: int = Field(ge=0)
    split_strategy: str
    train_row_ids_hash: str = Field(min_length=64, max_length=64)
    calibration_row_ids_hash: str = Field(min_length=64, max_length=64)
    test_row_ids_hash: str = Field(min_length=64, max_length=64)
    leakage_report_hash: str = Field(min_length=64, max_length=64)
    dataset_hash: str = Field(min_length=64, max_length=64)
    data_scope: PredictionDataScope = PredictionDataScope.SYNTHETIC
    source_high_watermarks: dict[str, str] = Field(default_factory=dict)
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    sufficiency_passed: bool = False
    sufficiency_report: dict[str, Any] = Field(default_factory=dict)
    train_row_ids: list[str] = Field(default_factory=list)
    calibration_row_ids: list[str] = Field(default_factory=list)
    test_row_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)


class LeakageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows_examined: int = Field(ge=0)
    rows_rejected: int = Field(ge=0)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    suspicious_features: list[str] = Field(default_factory=list)
    latest_source_timestamp: datetime | None = None
    cutoff_violations: int = Field(ge=0)
    clean: bool = True
    report_hash: str = Field(min_length=64, max_length=64)


# ---------------------------------------------------------------------------
# Models and evaluations
# ---------------------------------------------------------------------------
class PredictionModel(PredictionTenantScoped):
    prediction_model_id: str
    model_name: str
    model_type: str
    model_version: str
    target_definition: str = TARGET_DEFINITION
    horizon_days: int = DEFAULT_HORIZON_DAYS
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    label_version: str = LABEL_VERSION
    dataset_manifest_id: str
    training_code_version: str
    parameter_payload: dict[str, Any] = Field(default_factory=dict)
    parameter_hash: str = Field(min_length=64, max_length=64)
    training_seed: int
    trained_at: datetime
    model_state: ModelState = ModelState.CANDIDATE
    usage_scope: ModelUsageScope = ModelUsageScope.DEMO
    data_scope: PredictionDataScope = PredictionDataScope.SYNTHETIC
    production_eligible: bool = False
    promoted_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)

    @model_validator(mode="after")
    def _synthetic_guard(self) -> PredictionModel:
        if self.data_scope == PredictionDataScope.SYNTHETIC and self.production_eligible:
            raise ValueError("Synthetic models cannot be production_eligible")
        if (
            self.usage_scope == ModelUsageScope.PRODUCTION
            and self.data_scope == PredictionDataScope.SYNTHETIC
        ):
            raise ValueError("Synthetic models cannot have production usage_scope")
        return self


class PredictionModelEvaluation(PredictionTenantScoped):
    prediction_model_evaluation_id: str
    prediction_model_id: str
    dataset_manifest_id: str
    evaluation_split: EvaluationSplit
    evaluated_at: datetime
    row_count: int = Field(ge=0)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    brier_score: float
    log_loss: float
    roc_auc: float | None = None
    average_precision: float | None = None
    expected_calibration_error: float
    calibration_slope: float | None = None
    calibration_intercept: float | None = None
    baseline_brier_score: float
    baseline_log_loss: float
    confusion_matrix: dict[str, int] = Field(default_factory=dict)
    threshold_version: str
    reliability_bins: list[dict[str, float | int]] = Field(default_factory=list)
    evaluation_warnings: list[str] = Field(default_factory=list)
    passed_validation_gates: bool = False
    metrics_statistically_reliable: bool = False
    created_at: datetime | None = None

    @field_validator(
        "brier_score",
        "log_loss",
        "expected_calibration_error",
        "baseline_brier_score",
        "baseline_log_loss",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        result = _finite_or_none(value)
        assert result is not None
        return result


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
class PredictionRun(PredictionTenantScoped):
    prediction_run_id: str
    target_type: PredictionTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int = DEFAULT_HORIZON_DAYS
    model_id: str | None = None
    feature_snapshot_id: str
    state: PredictionRunState = PredictionRunState.PENDING
    started_at: datetime
    completed_at: datetime | None = None
    estimate_kind: EstimateKind | None = None
    sanitized_error_summary: str | None = Field(default=None, max_length=256)
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)


class DeliveryPrediction(PredictionTenantScoped):
    delivery_prediction_id: str
    prediction_run_id: str
    target_type: PredictionTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int = DEFAULT_HORIZON_DAYS
    estimate_kind: EstimateKind
    probability_of_delivery_success: float | None = None
    uncalibrated_risk_score: float | None = None
    risk_band: RiskBand
    model_id: str | None = None
    model_version: str | None = None
    baseline_version: str | None = None
    reliability_status: ReliabilityStatus
    applicability_status: ApplicabilityStatus
    data_scope: PredictionDataScope
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    prediction_hash: str = Field(min_length=64, max_length=64)
    data_quality_warnings: list[str] = Field(
        default_factory=list, max_length=MAX_DATA_QUALITY_WARNINGS
    )
    valid_until: datetime | None = None
    explanation_summary: str | None = Field(default=None, max_length=512)
    created_at: datetime | None = None

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, value: int) -> int:
        return validate_horizon(value)

    @field_validator("probability_of_delivery_success")
    @classmethod
    def _prob(cls, value: float | None) -> float | None:
        if value is None:
            return None
        value = _finite_or_none(value)
        assert value is not None
        if value < 0.0 or value > 1.0:
            raise ValueError("probability must be in [0, 1]")
        return value

    @field_validator("uncalibrated_risk_score")
    @classmethod
    def _score(cls, value: float | None) -> float | None:
        if value is None:
            return None
        value = _finite_or_none(value)
        assert value is not None
        if value < 0.0 or value > 100.0:
            raise ValueError("uncalibrated_risk_score must be in [0, 100]")
        return value

    @model_validator(mode="after")
    def _estimate_consistency(self) -> DeliveryPrediction:
        if self.estimate_kind == EstimateKind.CALIBRATED_PROBABILITY:
            if self.probability_of_delivery_success is None:
                raise ValueError("calibrated_probability requires probability field")
            if self.uncalibrated_risk_score is not None:
                raise ValueError("calibrated_probability must not expose uncalibrated_risk_score")
        elif self.estimate_kind == EstimateKind.UNCALIBRATED_SCORE:
            if self.uncalibrated_risk_score is None:
                raise ValueError("uncalibrated_score requires risk score")
            if self.probability_of_delivery_success is not None:
                raise ValueError("uncalibrated_score must not expose calibrated probability")
        elif self.estimate_kind == EstimateKind.INSUFFICIENT_DATA:
            if (
                self.probability_of_delivery_success is not None
                or self.uncalibrated_risk_score is not None
            ):
                raise ValueError("insufficient_data must not expose numeric estimates")
        return self


class PredictionFactor(PredictionTenantScoped):
    prediction_factor_id: str
    delivery_prediction_id: str
    rank: int = Field(ge=1, le=MAX_FACTORS)
    source_kind: FactorSourceKind
    feature_or_rule_id: str = Field(min_length=1, max_length=64)
    feature_label: str = Field(min_length=1, max_length=128)
    direction: str = Field(pattern="^(positive|negative)$")
    contribution: float
    feature_value: float | None = None
    normalized_value: float | None = None
    coefficient: float | None = None
    rule_version: str | None = Field(default=None, max_length=32)
    was_imputed: bool = False
    evidence_refs: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_REFS)
    lineage_summary: str | None = Field(default=None, max_length=256)
    created_at: datetime | None = None

    @field_validator("contribution", "feature_value", "normalized_value", "coefficient")
    @classmethod
    def _finite_optional(cls, value: float | None) -> float | None:
        return _finite_or_none(value)


# ---------------------------------------------------------------------------
# API / health response helpers
# ---------------------------------------------------------------------------
class PredictionDataHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    labeled_outcomes: int
    positive_outcomes: int
    negative_outcomes: int
    censored_outcomes: int
    feature_snapshots: int
    dataset_manifests: int
    active_models: int
    candidate_models: int
    predictions: int
    sufficiency: dict[str, Any]
    data_scope_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


class ScorecardResult(BaseModel):
    """Deterministic baseline output — never a calibrated probability."""

    model_config = ConfigDict(extra="forbid")

    estimate_kind: EstimateKind = EstimateKind.UNCALIBRATED_SCORE
    delivery_risk_score: float = Field(ge=0.0, le=100.0)
    risk_band: RiskBand
    positive_factors: list[dict[str, Any]] = Field(default_factory=list)
    negative_factors: list[dict[str, Any]] = Field(default_factory=list)
    missing_data_warnings: list[str] = Field(default_factory=list)
    scorecard_version: str


class DeliveryPredictionBundle(BaseModel):
    """API response bundling prediction + top factors."""

    model_config = ConfigDict(extra="forbid")

    prediction: DeliveryPrediction
    factors: list[PredictionFactor] = Field(default_factory=list, max_length=MAX_FACTORS)
    run: PredictionRun | None = None
