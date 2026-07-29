"""Prediction adapter for scenario baseline vs simulated estimates.

Preserves Prompt 4 model-gate rules. Failed/candidate models are never selected.
Fallback scorecard produces uncalibrated_score — never a probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import (
    SCORECARD_VERSION,
    TARGET_DEFINITION,
)
from app.domain.prediction_enums import EstimateKind, ModelUsageScope, RiskBand
from app.domain.scenario_enums import EstimateComparability
from app.domain.tenant_context import TenantContext
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.inference import risk_band_from_probability, risk_band_from_score
from app.services.prediction.training import predict_calibrated_proba, transform_snapshot
from app.services.scenarios.baseline import ScenarioBaseline


@dataclass
class ScenarioEstimate:
    estimate_kind: EstimateKind
    probability: float | None = None
    risk_score: float | None = None
    risk_band: RiskBand | None = None
    model_id: str | None = None
    baseline_version: str = SCORECARD_VERSION
    warnings: list[str] = field(default_factory=list)
    factors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScenarioPredictionPair:
    baseline: ScenarioEstimate
    simulated: ScenarioEstimate
    estimate_comparability: EstimateComparability
    probability_delta: float | None
    risk_score_delta: float | None


class ScenarioPredictionAdapter:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._scorecard = DeliveryScorecardV1()

    def evaluate_pair(
        self,
        ctx: TenantContext,
        *,
        baseline: ScenarioBaseline,
        simulated_feature_values: Mapping[str, float],
        force_model_id: str | None = None,
    ) -> ScenarioPredictionPair:
        """Evaluate baseline and simulated with the SAME estimate mechanism."""
        model = None
        if force_model_id:
            candidate = self._uow.prediction_models.get(ctx, force_model_id)
            state_val = None
            if candidate is not None:
                raw_state = getattr(candidate, "model_state", None)
                state_val = getattr(raw_state, "value", raw_state)
            if candidate is not None and state_val == "active" and candidate.parameter_payload:
                model = candidate
        if model is None:
            model = self._uow.prediction_models.get_active(
                ctx,
                target_definition=TARGET_DEFINITION,
                horizon_days=baseline.horizon_days,
                usage_scope=ModelUsageScope.DEMO,
            )

        state_val = None
        if model is not None:
            raw_state = getattr(model, "model_state", None)
            state_val = getattr(raw_state, "value", raw_state)
        use_calibrated = bool(
            model is not None and model.parameter_payload and state_val == "active"
        )

        if use_calibrated and model is not None:
            base_est = self._calibrated(model, baseline.feature_values)
            sim_est = self._calibrated(model, simulated_feature_values)
        else:
            base_est = self._scorecard_estimate(baseline.feature_values, baseline.missingness)
            sim_est = self._scorecard_estimate(simulated_feature_values, baseline.missingness)

        comparability, prob_delta, score_delta = self._compare(base_est, sim_est)
        return ScenarioPredictionPair(
            baseline=base_est,
            simulated=sim_est,
            estimate_comparability=comparability,
            probability_delta=prob_delta,
            risk_score_delta=score_delta,
        )

    def _scorecard_estimate(
        self, values: Mapping[str, float], missingness: Mapping[str, int]
    ) -> ScenarioEstimate:
        result = self._scorecard.score(values, missingness)
        score = float(result.delivery_risk_score)
        return ScenarioEstimate(
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            probability=None,
            risk_score=score,
            risk_band=risk_band_from_score(score),
            model_id=None,
            baseline_version=SCORECARD_VERSION,
            warnings=["baseline_fallback"],
            factors=list(getattr(result, "positive_factors", []) or [])[:4]
            + list(getattr(result, "negative_factors", []) or [])[:4],
        )

    def _calibrated(self, model: Any, values: Mapping[str, float]) -> ScenarioEstimate:
        from datetime import datetime, timezone

        from app.domain.prediction_enums import PredictionDataScope, PredictionTargetType
        from app.domain.prediction_models import PredictionFeatureSnapshot

        payload = model.parameter_payload or {}
        now = datetime.now(timezone.utc)
        snapshot = PredictionFeatureSnapshot(
            tenant_id=str(getattr(model, "tenant_id", "scenario")),
            prediction_feature_snapshot_id="scenario_overlay_ephemeral",
            target_type=PredictionTargetType.PROJECT,
            target_id="scenario_overlay",
            as_of_at=now,
            horizon_days=int(getattr(model, "horizon_days", 90) or 90),
            feature_schema_version="delivery_features_v1",
            feature_values={k: float(v) for k, v in values.items()},
            missingness_indicators={k: 0 for k in values},
            feature_lineage=[],
            source_high_watermarks={},
            evidence_cutoff_at=now,
            feature_hash="0" * 64,
            data_scope=PredictionDataScope.SYNTHETIC,
            data_quality_warnings=[],
        )
        normalized, _raw, _flags = transform_snapshot(snapshot, payload)
        proba = float(predict_calibrated_proba(normalized, payload))
        proba = max(0.0, min(1.0, proba))
        return ScenarioEstimate(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability=proba,
            risk_score=None,
            risk_band=risk_band_from_probability(proba),
            model_id=model.prediction_model_id,
            baseline_version=str(
                getattr(model, "model_version", None) or model.prediction_model_id
            ),
            warnings=[],
        )

    def _compare(
        self, baseline: ScenarioEstimate, simulated: ScenarioEstimate
    ) -> tuple[EstimateComparability, float | None, float | None]:
        if (
            baseline.estimate_kind == EstimateKind.INSUFFICIENT_DATA
            or simulated.estimate_kind == EstimateKind.INSUFFICIENT_DATA
        ):
            return EstimateComparability.INSUFFICIENT_DATA, None, None
        if baseline.estimate_kind != simulated.estimate_kind:
            return EstimateComparability.INCOMPARABLE_ESTIMATE_KIND, None, None
        if baseline.estimate_kind == EstimateKind.CALIBRATED_PROBABILITY:
            if baseline.probability is None or simulated.probability is None:
                return EstimateComparability.INSUFFICIENT_DATA, None, None
            return (
                EstimateComparability.COMPARABLE_PROBABILITY,
                float(simulated.probability) - float(baseline.probability),
                None,
            )
        if baseline.estimate_kind == EstimateKind.UNCALIBRATED_SCORE:
            if baseline.risk_score is None or simulated.risk_score is None:
                return EstimateComparability.INSUFFICIENT_DATA, None, None
            return (
                EstimateComparability.COMPARABLE_SCORE,
                None,
                float(simulated.risk_score) - float(baseline.risk_score),
            )
        return EstimateComparability.INCOMPARABLE_ESTIMATE_KIND, None, None
