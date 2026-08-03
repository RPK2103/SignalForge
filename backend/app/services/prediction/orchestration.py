"""High-level prediction pipeline facade used by the CLI."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import (
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    LABEL_VERSION,
    MIN_CALIBRATION_ROWS,
    MIN_LABELED_ROWS,
    MIN_NEGATIVE_ROWS,
    MIN_POSITIVE_ROWS,
    MIN_TEST_ROWS,
    MODEL_NAME,
    MODEL_TYPE,
    SCORECARD_VERSION,
    TARGET_DEFINITION,
    THRESHOLD_VERSION,
    TRAINING_CODE_VERSION,
)
from app.domain.prediction_enums import (
    EstimateKind,
    EvaluationSplit,
    ModelState,
    PredictionTargetType,
)
from app.domain.prediction_models import (
    DeliveryPredictionBundle,
    PredictionDataHealth,
    PredictionDatasetManifest,
    PredictionModel,
    PredictionModelEvaluation,
)
from app.domain.tenant_context import TenantContext
from app.observability.domain import record_prediction, record_prediction_validation
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission
from app.services.prediction.backtesting import PredictionBacktestService
from app.services.prediction.dataset_builder import PredictionDatasetBuilder
from app.services.prediction.evaluation import PredictionEvaluationService
from app.services.prediction.feature_schema import FEATURE_NAMES, feature_schema_hash
from app.services.prediction.inference import PredictionInferenceService
from app.services.prediction.registry import PredictionModelRegistry
from app.services.prediction.training import PredictionTrainingService

logger = logging.getLogger("signalforge.prediction")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(start: datetime, end: datetime) -> float:
    delta = (end - start).total_seconds() * 1000.0
    return delta if delta >= 0 else 0.0


def _record_prediction_telemetry(
    *, model_version: str, estimate_kind: EstimateKind | None, duration_ms: float
) -> None:
    """Emit one prediction telemetry sample per inference at the orchestrator boundary.

    An uncalibrated scorecard result is a deterministic fallback (never labelled a
    probability); insufficient evidence is a missing-data outcome, not a provider
    failure. Fail-open.
    """
    if estimate_kind is None:
        outcome = "error"
    else:
        outcome = estimate_kind.value
    record_prediction(
        model_version=model_version,
        outcome=outcome,
        duration_ms=duration_ms,
        fallback=estimate_kind == EstimateKind.UNCALIBRATED_SCORE,
        missing_data=estimate_kind == EstimateKind.INSUFFICIENT_DATA,
    )


def _validation_run_outcome(
    *, model: PredictionModel, evaluation: PredictionModelEvaluation
) -> str:
    """Map a persisted evaluation onto the bounded validation-run vocabulary."""
    if model.model_state == ModelState.REJECTED:
        return "rejected"
    warnings = list(evaluation.evaluation_warnings or [])
    if evaluation.row_count == 0 or "empty_evaluation_split" in warnings:
        return "insufficient_data"
    if "gate_fail_sufficiency" in warnings:
        return "insufficient_data"
    if evaluation.passed_validation_gates:
        return "passed"
    return "failed"


class PredictionOrchestrator:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._datasets = PredictionDatasetBuilder(uow)
        self._training = PredictionTrainingService(uow)
        self._evaluation = PredictionEvaluationService(uow)
        self._registry = PredictionModelRegistry(uow)
        self._inference = PredictionInferenceService(uow)
        self._backtesting = PredictionBacktestService(uow)
        self._authz = AuthorizationService()

    # Public alias used by API/CLI.
    @property
    def inference(self) -> PredictionInferenceService:
        return self._inference

    @property
    def registry(self) -> PredictionModelRegistry:
        return self._registry

    def build_dataset(
        self,
        ctx: TenantContext,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> PredictionDatasetManifest:
        return self._datasets.build(ctx, horizon_days=horizon_days)

    def train(
        self,
        ctx: TenantContext,
        manifest_id: str,
        seed: int = 42,
    ) -> PredictionModel:
        return self._training.train(ctx, manifest_id, seed=seed)

    def evaluate(
        self,
        ctx: TenantContext,
        model_id: str,
        split: EvaluationSplit = EvaluationSplit.TEST,
        *,
        security: SecurityContext,
        mark_validated_if_passing: bool = False,
    ) -> PredictionModelEvaluation:
        """Run a model evaluation / validation-gate check.

        ``security`` is required (no optional bypass). ``predictions.validate``
        is always re-checked; authorization denial emits no validation metric.
        CLI/batch callers must pass an explicit trusted
        ``internal_system_context``. A successful evaluation queues
        ``record_prediction_validation`` until the enclosing UoW commits.
        """
        self._authz.require(security, Permission.PREDICTIONS_VALIDATE, ctx.tenant_id)

        model = self._uow.prediction_models.get(ctx, model_id)
        model_version = (model.model_version if model is not None else None) or "none"
        try:
            evaluation = self._evaluation.evaluate(ctx, model_id, split=split)
        except Exception:
            record_prediction_validation(
                model_version=model_version,
                outcome="error",
                evaluation_type=split.value,
            )
            raise

        if (
            mark_validated_if_passing
            and evaluation.passed_validation_gates
            and split == EvaluationSplit.TEST
        ):
            try:
                self._evaluation.mark_validated(
                    ctx,
                    model_id,
                    evaluation_id=evaluation.prediction_model_evaluation_id,
                )
            except ValueError as exc:
                logger.info(
                    "prediction.orchestrator.validate_skipped tenant_id=%s model_id=%s reason=%s",
                    ctx.tenant_id,
                    model_id,
                    str(exc),
                )

        # Re-load model in case mark_validated changed state; outcome uses the
        # pre-promotion evaluation result plus current model state.
        model_after = self._uow.prediction_models.get(ctx, model_id) or model
        if model_after is None:
            outcome = "error"
            version = model_version
        else:
            outcome = _validation_run_outcome(model=model_after, evaluation=evaluation)
            version = model_after.model_version or "none"
        eval_type = split.value
        self._uow.note_pending_telemetry(
            lambda mv=version, o=outcome, et=eval_type: record_prediction_validation(
                model_version=mv,
                outcome=o,
                evaluation_type=et,
            )
        )
        return evaluation

    def promote(
        self,
        ctx: TenantContext,
        model_id: str,
        *,
        confirm: bool = False,
    ) -> PredictionModel:
        return self._registry.promote(ctx, model_id, confirm=confirm)

    def retire(self, ctx: TenantContext, model_id: str) -> PredictionModel:
        return self._registry.retire(ctx, model_id)

    def predict(
        self,
        ctx: TenantContext,
        target_type: PredictionTargetType | str,
        target_id: str,
        as_of_at: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> DeliveryPredictionBundle:
        when = as_of_at or _utcnow()
        started = _utcnow()
        try:
            bundle = self._inference.predict(
                ctx,
                target_type,
                target_id,
                when,
                horizon_days=horizon_days,
            )
        except Exception:
            _record_prediction_telemetry(
                model_version="none",
                estimate_kind=None,
                duration_ms=_duration_ms(started, _utcnow()),
            )
            raise
        # Defer success telemetry until the enclosing UoW commits so a later
        # rollback never reports a false committed-success prediction.
        model_version = bundle.prediction.model_version or "none"
        estimate_kind = bundle.prediction.estimate_kind
        duration = _duration_ms(started, _utcnow())
        self._uow.note_pending_telemetry(
            lambda mv=model_version, ek=estimate_kind, d=duration: _record_prediction_telemetry(
                model_version=mv,
                estimate_kind=ek,
                duration_ms=d,
            )
        )
        return bundle

    def backtest(
        self,
        ctx: TenantContext,
        *,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        max_folds: int | None = None,
        seed: int = 42,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "horizon_days": horizon_days,
            "seed": seed,
        }
        if max_folds is not None:
            kwargs["max_folds"] = max_folds
        return self._backtesting.run(ctx, **kwargs)

    def list_models(
        self,
        ctx: TenantContext,
        *,
        state: ModelState | None = None,
        horizon_days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PredictionModel]:
        return self._registry.list(
            ctx, state=state, horizon_days=horizon_days, limit=limit, offset=offset
        )

    def list_evaluations(
        self,
        ctx: TenantContext,
        *,
        model_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PredictionModelEvaluation]:
        if model_id:
            page = self._uow.prediction_evaluations.list_for_model(
                ctx, model_id, limit=limit, offset=offset
            )
        else:
            page = self._uow.prediction_evaluations.list(ctx, limit=limit, offset=offset)
        return list(page.items)

    def data_health(self, ctx: TenantContext) -> PredictionDataHealth:
        labeled = positive = negative = censored = 0
        data_scope_counts: dict[str, int] = {}
        warnings: list[str] = []

        outcomes = self._uow.delivery_outcomes.list_for_horizon(
            ctx, horizon_days=DEFAULT_HORIZON_DAYS, limit=500, offset=0
        )

        for outcome in outcomes:
            scope = getattr(outcome.data_scope, "value", str(outcome.data_scope))
            data_scope_counts[scope] = data_scope_counts.get(scope, 0) + 1
            category = getattr(outcome.outcome_category, "value", str(outcome.outcome_category))
            if category in {"unknown", "censored"}:
                censored += 1
                continue
            if outcome.binary_label in (0, 1):
                labeled += 1
                if outcome.binary_label == 1:
                    positive += 1
                else:
                    negative += 1

        feature_snapshots = self._count(ctx, "prediction_feature_snapshots")
        dataset_manifests = self._count(ctx, "prediction_datasets")
        predictions = self._count(ctx, "delivery_predictions")

        active_models = len(self._registry.list(ctx, state=ModelState.ACTIVE, limit=100))
        candidate_models = len(self._registry.list(ctx, state=ModelState.CANDIDATE, limit=100))

        sufficiency = {
            "min_labeled_rows": {
                "required": MIN_LABELED_ROWS,
                "actual": labeled,
                "passed": labeled >= MIN_LABELED_ROWS,
            },
            "min_positive_rows": {
                "required": MIN_POSITIVE_ROWS,
                "actual": positive,
                "passed": positive >= MIN_POSITIVE_ROWS,
            },
            "min_negative_rows": {
                "required": MIN_NEGATIVE_ROWS,
                "actual": negative,
                "passed": negative >= MIN_NEGATIVE_ROWS,
            },
            "min_calibration_rows": {"required": MIN_CALIBRATION_ROWS},
            "min_test_rows": {"required": MIN_TEST_ROWS},
        }
        if labeled < MIN_LABELED_ROWS:
            warnings.append("insufficient_labeled_outcomes")
        if positive < MIN_POSITIVE_ROWS or negative < MIN_NEGATIVE_ROWS:
            warnings.append("class_imbalance_or_missing_class")
        if active_models == 0:
            warnings.append("no_active_model")

        return PredictionDataHealth(
            tenant_id=ctx.tenant_id,
            labeled_outcomes=labeled,
            positive_outcomes=positive,
            negative_outcomes=negative,
            censored_outcomes=censored,
            feature_snapshots=feature_snapshots,
            dataset_manifests=dataset_manifests,
            active_models=active_models,
            candidate_models=candidate_models,
            predictions=predictions,
            sufficiency=sufficiency,
            data_scope_counts=data_scope_counts,
            warnings=warnings,
        )

    def validate_pipeline(self, ctx: TenantContext) -> dict[str, Any]:
        """Sanity-check version wiring and repository availability (no training)."""
        checks: dict[str, Any] = {}
        schema_hash = feature_schema_hash()
        checks["feature_schema"] = {
            "version": FEATURE_SCHEMA_VERSION,
            "feature_count": len(FEATURE_NAMES),
            "schema_hash": schema_hash,
            "passed": len(FEATURE_NAMES) >= 30 and len(schema_hash) == 64,
        }
        checks["constants"] = {
            "target_definition": TARGET_DEFINITION,
            "label_version": LABEL_VERSION,
            "scorecard_version": SCORECARD_VERSION,
            "model_name": MODEL_NAME,
            "model_type": MODEL_TYPE,
            "threshold_version": THRESHOLD_VERSION,
            "training_code_version": TRAINING_CODE_VERSION,
            "passed": True,
        }
        repo_names = [
            "delivery_outcomes",
            "prediction_feature_snapshots",
            "prediction_datasets",
            "prediction_models",
            "prediction_evaluations",
            "prediction_runs",
            "delivery_predictions",
            "prediction_factors",
        ]
        repo_status: dict[str, bool] = {}
        for name in repo_names:
            repo_status[name] = hasattr(self._uow, name)
        checks["repositories"] = {
            "status": repo_status,
            "passed": all(repo_status.values()),
        }
        health = self.data_health(ctx)
        checks["data_health"] = {
            "labeled_outcomes": health.labeled_outcomes,
            "warnings": health.warnings,
            "passed": health.labeled_outcomes >= 0,
        }
        passed = all(bool(item.get("passed")) for item in checks.values())
        result = {
            "tenant_id": ctx.tenant_id,
            "passed": passed,
            "checks": checks,
            "validated_at": _utcnow().isoformat(),
        }
        logger.info(
            "prediction.pipeline.validated tenant_id=%s passed=%s",
            ctx.tenant_id,
            passed,
        )
        return result

    def _count(self, ctx: TenantContext, repo_attr: str) -> int:
        repo = getattr(self._uow, repo_attr, None)
        if repo is None:
            return 0
        count_fn = getattr(repo, "count", None)
        if callable(count_fn):
            try:
                return int(count_fn(ctx))
            except TypeError:
                return int(count_fn(ctx, limit=10_000))
        list_fn = getattr(repo, "list", None)
        if callable(list_fn):
            try:
                result = list_fn(ctx, limit=10_000)
            except TypeError:
                result = list_fn(ctx)
            if hasattr(result, "items"):
                return len(result.items)
            if hasattr(result, "total"):
                return int(result.total)
            return len(list(result))
        return 0


# Canonical name for API / CLI consumers.
PredictionOrchestrationService = PredictionOrchestrator
