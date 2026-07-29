"""Delivery prediction inference — calibrated model or scorecard fallback."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import (
    BAND_HIGH_MAX,
    BAND_LOW_MAX,
    BAND_MODERATE_MAX,
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    SCORECARD_VERSION,
    SUPPORTED_HORIZONS,
)
from app.domain.prediction_enums import (
    ApplicabilityStatus,
    EstimateKind,
    ModelState,
    ModelUsageScope,
    PredictionDataQualityWarning,
    PredictionDataScope,
    PredictionRunState,
    PredictionTargetType,
    ReliabilityStatus,
    RiskBand,
)
from app.domain.prediction_models import (
    DeliveryPrediction,
    DeliveryPredictionBundle,
    PredictionFactor,
    PredictionFeatureSnapshot,
    PredictionModel,
    PredictionRun,
    ScorecardResult,
    validate_horizon,
)
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.applicability import (
    check_applicability,
    training_feature_ranges,
    training_missing_rates,
)
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.explanations import (
    build_explanation_summary,
    build_logistic_factors,
    build_scorecard_factors,
)
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.prediction.registry import PredictionModelRegistry
from app.services.prediction.training import (
    predict_calibrated_proba,
    transform_snapshot,
)

logger = logging.getLogger("signalforge.prediction")

_CRITICAL_FEATURES = (
    "readiness_score_at_cutoff",
    "active_dependency_count",
    "open_work_item_count",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def risk_band_from_score(score: float) -> RiskBand:
    if score <= BAND_LOW_MAX:
        return RiskBand.LOW
    if score <= BAND_MODERATE_MAX:
        return RiskBand.MODERATE
    if score <= BAND_HIGH_MAX:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def risk_band_from_probability(probability: float) -> RiskBand:
    return risk_band_from_score((1.0 - float(probability)) * 100.0)


class PredictionInferenceService:
    """Produce immutable delivery predictions. Never mutates Phase 2 assessments."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._extractor = FeatureExtractor(uow)
        self._registry = PredictionModelRegistry(uow)
        self._scorecard = DeliveryScorecardV1()

    def predict(
        self,
        ctx: TenantContext,
        target_type: PredictionTargetType | str,
        target_id: str,
        as_of_at: datetime,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> DeliveryPredictionBundle:
        if isinstance(target_type, str):
            target_type = PredictionTargetType(target_type)
        try:
            horizon_days = validate_horizon(horizon_days)
        except ValueError:
            return self._insufficient_bundle(
                ctx,
                target_type=target_type,
                target_id=target_id,
                as_of_at=as_of_at,
                horizon_days=horizon_days
                if horizon_days in SUPPORTED_HORIZONS
                else DEFAULT_HORIZON_DAYS,
                warnings=[PredictionDataQualityWarning.UNSUPPORTED_HORIZON.value],
                reliability=ReliabilityStatus.INSUFFICIENT_HISTORY,
            )

        started = _utcnow()
        target_resolved = self._resolve_target(ctx, target_type, target_id)

        snapshot = self._extractor.extract(
            ctx,
            target_type,
            target_id,
            as_of_at,
            horizon_days=horizon_days,
            data_scope=PredictionDataScope.SYNTHETIC,
        )

        run = PredictionRun(
            tenant_id=ctx.tenant_id,
            prediction_run_id=build_entity_id(
                "prun",
                ctx.tenant_id,
                target_type.value,
                target_id,
                as_of_at.isoformat(),
                str(horizon_days),
                started.isoformat(),
            ),
            target_type=target_type,
            target_id=target_id,
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            model_id=None,
            feature_snapshot_id=snapshot.prediction_feature_snapshot_id,
            state=PredictionRunState.RUNNING,
            started_at=started,
            completed_at=None,
            estimate_kind=None,
            sanitized_error_summary=None,
            created_at=started,
        )
        self._uow.prediction_runs.insert(ctx, run)

        critical_missing = self._critical_missing(snapshot)
        if not target_resolved or critical_missing:
            warnings = []
            if not target_resolved:
                warnings.append(PredictionDataQualityWarning.UNRESOLVED_TARGET.value)
            if critical_missing:
                warnings.append(PredictionDataQualityWarning.HIGH_MISSINGNESS.value)
                warnings.append(PredictionDataQualityWarning.INSUFFICIENT_HISTORY.value)
            bundle = self._finalize_insufficient(
                ctx,
                run=run,
                snapshot=snapshot,
                warnings=warnings,
            )
            return bundle

        model = self._registry.get_active(
            ctx,
            horizon_days=horizon_days,
            usage_scope=ModelUsageScope.DEMO,
        )
        use_calibrated = (
            model is not None and model.model_state == ModelState.ACTIVE and model.parameter_payload
        )

        training_ranges = training_feature_ranges(model.parameter_payload) if model else None
        missing_rates = training_missing_rates(model.parameter_payload) if model else None
        applicability, reliability, dq_warnings = check_applicability(
            snapshot=snapshot,
            model=model if use_calibrated else None,
            horizon_days=horizon_days,
            training_ranges=training_ranges,
            train_missing_rates=missing_rates,
            target_resolved=target_resolved,
            critical_missing_features=critical_missing or None,
        )

        if use_calibrated and model is not None:
            prediction, factors = self._calibrated_path(
                ctx,
                run=run,
                snapshot=snapshot,
                model=model,
                applicability=applicability,
                reliability=reliability,
                warnings=dq_warnings,
            )
        else:
            if PredictionDataQualityWarning.BASELINE_FALLBACK.value not in dq_warnings:
                dq_warnings.append(PredictionDataQualityWarning.BASELINE_FALLBACK.value)
            prediction, factors = self._scorecard_path(
                ctx,
                run=run,
                snapshot=snapshot,
                applicability=applicability,
                reliability=reliability
                if reliability != ReliabilityStatus.VALIDATED
                else ReliabilityStatus.MODEL_UNAVAILABLE,
                warnings=dq_warnings,
            )

        run.model_id = prediction.model_id
        run.estimate_kind = prediction.estimate_kind
        run.state = PredictionRunState.SUCCEEDED
        run.completed_at = _utcnow()
        self._update_run(ctx, run)

        prediction, factors = self._persist_immutable_prediction(ctx, prediction, factors)

        logger.info(
            "prediction.inference.completed tenant_id=%s target=%s/%s estimate_kind=%s run_id=%s",
            ctx.tenant_id,
            target_type.value,
            target_id,
            prediction.estimate_kind.value,
            run.prediction_run_id,
        )
        return DeliveryPredictionBundle(
            prediction=prediction,
            factors=factors,
            run=run,
        )

    def _calibrated_path(
        self,
        ctx: TenantContext,
        *,
        run: PredictionRun,
        snapshot: PredictionFeatureSnapshot,
        model: PredictionModel,
        applicability: ApplicabilityStatus,
        reliability: ReliabilityStatus,
        warnings: list[str],
    ) -> tuple[DeliveryPrediction, list[PredictionFactor]]:
        normalized, raw_values, imputed_flags = transform_snapshot(
            snapshot, model.parameter_payload
        )
        probability = predict_calibrated_proba(normalized, model.parameter_payload)
        probability = max(0.0, min(1.0, float(probability)))
        band = risk_band_from_probability(probability)

        if model.data_scope == PredictionDataScope.SYNTHETIC:
            if PredictionDataQualityWarning.SYNTHETIC_MODEL.value not in warnings:
                warnings.append(PredictionDataQualityWarning.SYNTHETIC_MODEL.value)
            if reliability == ReliabilityStatus.VALIDATED:
                reliability = ReliabilityStatus.LIMITED

        feature_list = list(model.parameter_payload["feature_list"])
        coefficients = [float(c) for c in model.parameter_payload["coefficients"]]
        pred_id = build_entity_id(
            "dpred",
            ctx.tenant_id,
            run.prediction_run_id,
            "calibrated",
        )
        factors = build_logistic_factors(
            ctx,
            delivery_prediction_id=pred_id,
            snapshot=snapshot,
            feature_list=feature_list,
            coefficients=coefficients,
            normalized_values=normalized,
            raw_values=raw_values,
            imputed_flags=imputed_flags,
        )
        explanation = build_explanation_summary(factors, reduced=probability < 0.5)
        body = {
            "tenant_id": ctx.tenant_id,
            "target_type": run.target_type.value,
            "target_id": run.target_id,
            "as_of_at": run.as_of_at.isoformat(),
            "horizon_days": run.horizon_days,
            "estimate_kind": EstimateKind.CALIBRATED_PROBABILITY.value,
            "probability_of_delivery_success": probability,
            "model_id": model.prediction_model_id,
            "model_version": model.model_version,
            "feature_snapshot_id": snapshot.prediction_feature_snapshot_id,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "parameter_hash": model.parameter_hash,
        }
        prediction_hash = snapshot_hash(body)
        pred_id = build_entity_id("dpred", ctx.tenant_id, prediction_hash[:24])
        # Rebuild factors bound to final prediction id.
        factors = build_logistic_factors(
            ctx,
            delivery_prediction_id=pred_id,
            snapshot=snapshot,
            feature_list=feature_list,
            coefficients=coefficients,
            normalized_values=normalized,
            raw_values=raw_values,
            imputed_flags=imputed_flags,
        )
        prediction = DeliveryPrediction(
            tenant_id=ctx.tenant_id,
            delivery_prediction_id=pred_id,
            prediction_run_id=run.prediction_run_id,
            target_type=run.target_type,
            target_id=run.target_id,
            as_of_at=run.as_of_at,
            horizon_days=run.horizon_days,
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=probability,
            uncalibrated_risk_score=None,
            risk_band=band,
            model_id=model.prediction_model_id,
            model_version=model.model_version,
            baseline_version=None,
            reliability_status=reliability,
            applicability_status=applicability,
            data_scope=model.data_scope,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            prediction_hash=prediction_hash,
            data_quality_warnings=warnings[:32],
            valid_until=run.as_of_at + timedelta(days=run.horizon_days),
            explanation_summary=explanation,
            created_at=_utcnow(),
        )
        return prediction, factors

    def _scorecard_path(
        self,
        ctx: TenantContext,
        *,
        run: PredictionRun,
        snapshot: PredictionFeatureSnapshot,
        applicability: ApplicabilityStatus,
        reliability: ReliabilityStatus,
        warnings: list[str],
    ) -> tuple[DeliveryPrediction, list[PredictionFactor]]:
        scorecard: ScorecardResult = self._scorecard.score(
            snapshot.feature_values, snapshot.missingness_indicators
        )
        for warning in scorecard.missing_data_warnings:
            if warning not in warnings:
                warnings.append(warning)

        body = {
            "tenant_id": ctx.tenant_id,
            "target_type": run.target_type.value,
            "target_id": run.target_id,
            "as_of_at": run.as_of_at.isoformat(),
            "horizon_days": run.horizon_days,
            "estimate_kind": EstimateKind.UNCALIBRATED_SCORE.value,
            "uncalibrated_risk_score": scorecard.delivery_risk_score,
            "baseline_version": scorecard.scorecard_version or SCORECARD_VERSION,
            "feature_snapshot_id": snapshot.prediction_feature_snapshot_id,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        }
        prediction_hash = snapshot_hash(body)
        pred_id = build_entity_id("dpred", ctx.tenant_id, prediction_hash[:24])
        factors = build_scorecard_factors(
            ctx,
            delivery_prediction_id=pred_id,
            scorecard=scorecard,
        )
        explanation = build_explanation_summary(
            factors, reduced=scorecard.delivery_risk_score > BAND_MODERATE_MAX
        )
        prediction = DeliveryPrediction(
            tenant_id=ctx.tenant_id,
            delivery_prediction_id=pred_id,
            prediction_run_id=run.prediction_run_id,
            target_type=run.target_type,
            target_id=run.target_id,
            as_of_at=run.as_of_at,
            horizon_days=run.horizon_days,
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            probability_of_delivery_success=None,
            uncalibrated_risk_score=float(scorecard.delivery_risk_score),
            risk_band=scorecard.risk_band,
            model_id=None,
            model_version=None,
            baseline_version=scorecard.scorecard_version or SCORECARD_VERSION,
            reliability_status=reliability,
            applicability_status=applicability,
            data_scope=snapshot.data_scope,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            prediction_hash=prediction_hash,
            data_quality_warnings=warnings[:32],
            valid_until=run.as_of_at + timedelta(days=run.horizon_days),
            explanation_summary=explanation,
            created_at=_utcnow(),
        )
        return prediction, factors

    def _finalize_insufficient(
        self,
        ctx: TenantContext,
        *,
        run: PredictionRun,
        snapshot: PredictionFeatureSnapshot,
        warnings: list[str],
    ) -> DeliveryPredictionBundle:
        applicability, reliability, extra = check_applicability(
            snapshot=snapshot,
            model=None,
            horizon_days=run.horizon_days,
            target_resolved=PredictionDataQualityWarning.UNRESOLVED_TARGET.value not in warnings,
            critical_missing_features=["critical"]
            if PredictionDataQualityWarning.HIGH_MISSINGNESS.value in warnings
            else None,
        )
        for item in extra:
            if item not in warnings:
                warnings.append(item)

        body = {
            "tenant_id": ctx.tenant_id,
            "target_type": run.target_type.value,
            "target_id": run.target_id,
            "as_of_at": run.as_of_at.isoformat(),
            "horizon_days": run.horizon_days,
            "estimate_kind": EstimateKind.INSUFFICIENT_DATA.value,
            "feature_snapshot_id": snapshot.prediction_feature_snapshot_id,
            "warnings": sorted(warnings),
        }
        prediction_hash = snapshot_hash(body)
        pred_id = build_entity_id("dpred", ctx.tenant_id, prediction_hash[:24])
        prediction = DeliveryPrediction(
            tenant_id=ctx.tenant_id,
            delivery_prediction_id=pred_id,
            prediction_run_id=run.prediction_run_id,
            target_type=run.target_type,
            target_id=run.target_id,
            as_of_at=run.as_of_at,
            horizon_days=run.horizon_days,
            estimate_kind=EstimateKind.INSUFFICIENT_DATA,
            probability_of_delivery_success=None,
            uncalibrated_risk_score=None,
            risk_band=RiskBand.HIGH,
            model_id=None,
            model_version=None,
            baseline_version=None,
            reliability_status=reliability
            if reliability != ReliabilityStatus.MODEL_UNAVAILABLE
            else ReliabilityStatus.INSUFFICIENT_HISTORY,
            applicability_status=ApplicabilityStatus.NOT_APPLICABLE,
            data_scope=snapshot.data_scope,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            prediction_hash=prediction_hash,
            data_quality_warnings=warnings[:32],
            valid_until=None,
            explanation_summary=("Insufficient delivery evidence to produce a numeric estimate."),
            created_at=_utcnow(),
        )
        run.estimate_kind = EstimateKind.INSUFFICIENT_DATA
        run.state = PredictionRunState.SUCCEEDED
        run.completed_at = _utcnow()
        self._update_run(ctx, run)
        prediction, factors = self._persist_immutable_prediction(ctx, prediction, [])
        return DeliveryPredictionBundle(prediction=prediction, factors=factors, run=run)

    def _insufficient_bundle(
        self,
        ctx: TenantContext,
        *,
        target_type: PredictionTargetType,
        target_id: str,
        as_of_at: datetime,
        horizon_days: int,
        warnings: list[str],
        reliability: ReliabilityStatus,
    ) -> DeliveryPredictionBundle:
        started = _utcnow()
        # Minimal run without feature snapshot persistence when horizon invalid.
        snap_id = build_entity_id(
            "pfs",
            ctx.tenant_id,
            target_type.value,
            target_id,
            as_of_at.isoformat(),
            str(horizon_days),
            "insufficient",
        )
        run = PredictionRun(
            tenant_id=ctx.tenant_id,
            prediction_run_id=build_entity_id(
                "prun",
                ctx.tenant_id,
                target_type.value,
                target_id,
                as_of_at.isoformat(),
                str(horizon_days),
                "insufficient",
            ),
            target_type=target_type,
            target_id=target_id,
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            model_id=None,
            feature_snapshot_id=snap_id,
            state=PredictionRunState.SUCCEEDED,
            started_at=started,
            completed_at=started,
            estimate_kind=EstimateKind.INSUFFICIENT_DATA,
            sanitized_error_summary="unsupported_or_insufficient_input",
            created_at=started,
        )
        body = {
            "tenant_id": ctx.tenant_id,
            "target_type": target_type.value,
            "target_id": target_id,
            "as_of_at": as_of_at.isoformat(),
            "horizon_days": horizon_days,
            "estimate_kind": EstimateKind.INSUFFICIENT_DATA.value,
            "warnings": sorted(warnings),
        }
        prediction_hash = snapshot_hash(body)
        prediction = DeliveryPrediction(
            tenant_id=ctx.tenant_id,
            delivery_prediction_id=build_entity_id("dpred", ctx.tenant_id, prediction_hash[:24]),
            prediction_run_id=run.prediction_run_id,
            target_type=target_type,
            target_id=target_id,
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            estimate_kind=EstimateKind.INSUFFICIENT_DATA,
            probability_of_delivery_success=None,
            uncalibrated_risk_score=None,
            risk_band=RiskBand.HIGH,
            model_id=None,
            model_version=None,
            baseline_version=None,
            reliability_status=reliability,
            applicability_status=ApplicabilityStatus.NOT_APPLICABLE,
            data_scope=PredictionDataScope.SYNTHETIC,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            prediction_hash=prediction_hash,
            data_quality_warnings=warnings[:32],
            valid_until=None,
            explanation_summary=("Insufficient delivery evidence to produce a numeric estimate."),
            created_at=started,
        )
        existing_run = self._uow.prediction_runs.get(ctx, run.prediction_run_id)
        if existing_run is None:
            self._uow.prediction_runs.insert(ctx, run)
        else:
            run = existing_run
        prediction, factors = self._persist_immutable_prediction(ctx, prediction, [])
        return DeliveryPredictionBundle(prediction=prediction, factors=factors, run=run)

    def _persist_immutable_prediction(
        self,
        ctx: TenantContext,
        prediction: DeliveryPrediction,
        factors: list,
    ) -> tuple[DeliveryPrediction, list]:
        """Insert prediction once; identical hashes return the existing immutable row."""
        get_by_hash = getattr(self._uow.delivery_predictions, "get_by_hash", None)
        if callable(get_by_hash):
            existing = get_by_hash(ctx, prediction.prediction_hash)
            if existing is not None:
                list_fn = getattr(self._uow.prediction_factors, "list_for_prediction", None)
                if callable(list_fn):
                    return existing, list(list_fn(ctx, existing.delivery_prediction_id))
                return existing, []
        existing_by_id = self._uow.delivery_predictions.get(ctx, prediction.delivery_prediction_id)
        if existing_by_id is not None:
            list_fn = getattr(self._uow.prediction_factors, "list_for_prediction", None)
            if callable(list_fn):
                return existing_by_id, list(list_fn(ctx, existing_by_id.delivery_prediction_id))
            return existing_by_id, []
        self._uow.delivery_predictions.insert(ctx, prediction)
        insert_many = getattr(self._uow.prediction_factors, "insert_many", None)
        if factors:
            if callable(insert_many):
                insert_many(ctx, factors)
            else:
                for factor in factors:
                    self._uow.prediction_factors.insert(ctx, factor)
        return prediction, factors

    def _resolve_target(
        self,
        ctx: TenantContext,
        target_type: PredictionTargetType,
        target_id: str,
    ) -> bool:
        repo = self._uow.initiatives_projects
        if target_type == PredictionTargetType.PROJECT:
            getter = getattr(repo, "get_project", None) or getattr(repo, "get", None)
        else:
            getter = getattr(repo, "get_initiative", None) or getattr(repo, "get", None)
        if not callable(getter):
            return True  # soft-pass if catalog API differs; extractor still runs
        try:
            entity = getter(ctx, target_id)
        except TypeError:
            try:
                entity = getter(ctx, target_type=target_type.value, target_id=target_id)
            except TypeError:
                return True
        return entity is not None

    @staticmethod
    def _critical_missing(snapshot: PredictionFeatureSnapshot) -> list[str]:
        missing: list[str] = []
        for name in _CRITICAL_FEATURES:
            value = snapshot.feature_values.get(name)
            flag = int(snapshot.missingness_indicators.get(name, 0))
            if value is None or flag == 1:
                missing.append(name)
        # Require majority of critical features present.
        if len(missing) >= max(2, len(_CRITICAL_FEATURES) - 1):
            return missing
        return []

    def _update_run(self, ctx: TenantContext, run: PredictionRun) -> None:
        update = getattr(self._uow.prediction_runs, "update", None)
        if callable(update):
            update(ctx, run)
        else:
            self._uow.prediction_runs.insert(ctx, run)
