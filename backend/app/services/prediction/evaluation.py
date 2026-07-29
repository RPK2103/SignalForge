"""Model evaluation metrics, baseline comparison, and validation gates."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import (
    GATE_MAX_BASELINE_BRIER_DELTA,
    GATE_MAX_BRIER,
    GATE_MAX_ECE,
    THRESHOLD_VERSION,
)
from app.domain.prediction_enums import (
    EvaluationSplit,
    ModelState,
    PredictionDataScope,
)
from app.domain.prediction_models import (
    PredictionModel,
    PredictionModelEvaluation,
)
from app.domain.tenant_context import TenantContext
from app.services.prediction import math_utils
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.training import (
    PredictionTrainingService,
    predict_calibrated_proba,
    transform_snapshot,
)

logger = logging.getLogger("signalforge.prediction")

# Baseline risk score -> pseudo-probability conversion is ONLY for internal
# metric comparability against Brier/log-loss. It does NOT claim the scorecard
# is calibrated. Do not expose this conversion as a calibrated probability.
_BASELINE_PSEUDO_PROB_NOTE = (
    "baseline_pseudo_prob = 1 - delivery_risk_score/100 "
    "(metric comparison only; not a calibrated probability)"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def baseline_pseudo_probability(delivery_risk_score: float) -> float:
    """Map uncalibrated 0–100 risk score to a pseudo-probability for metrics only."""
    score = max(0.0, min(100.0, float(delivery_risk_score)))
    return 1.0 - (score / 100.0)


class PredictionEvaluationService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._scorecard = DeliveryScorecardV1()
        self._training_loader = PredictionTrainingService(uow)

    def evaluate(
        self,
        ctx: TenantContext,
        model_id: str,
        split: EvaluationSplit = EvaluationSplit.TEST,
    ) -> PredictionModelEvaluation:
        model = self._uow.prediction_models.get(ctx, model_id)
        if model is None:
            raise LookupError(f"Prediction model not found: {model_id}")

        manifest = self._uow.prediction_datasets.get(ctx, model.dataset_manifest_id)
        if manifest is None:
            raise LookupError(f"Dataset manifest not found: {model.dataset_manifest_id}")

        rows = self._training_loader._load_split_rows(ctx, manifest, split)
        y_true = [int(o.binary_label or 0) for o, _ in rows]
        model_probs: list[float] = []
        baseline_probs: list[float] = []
        warnings: list[str] = []

        if model.data_scope == PredictionDataScope.SYNTHETIC:
            warnings.append("synthetic_data_scope: metrics reflect demo/synthetic validation only")
        warnings.append(_BASELINE_PSEUDO_PROB_NOTE)

        payload = model.parameter_payload
        for outcome, snapshot in rows:
            normalized, _, _ = transform_snapshot(snapshot, payload)
            prob = predict_calibrated_proba(normalized, payload)
            if not math.isfinite(prob) or prob < 0.0 or prob > 1.0:
                warnings.append("non_finite_or_oob_probability")
                prob = max(0.0, min(1.0, float(prob) if math.isfinite(prob) else 0.5))
            model_probs.append(prob)

            scorecard = self._scorecard.score(
                snapshot.feature_values, snapshot.missingness_indicators
            )
            baseline_probs.append(baseline_pseudo_probability(scorecard.delivery_risk_score))

        row_count = len(y_true)
        positive_count = sum(y_true)
        negative_count = row_count - positive_count

        if row_count == 0:
            brier = 1.0
            log_loss = 1.0
            ece = 1.0
            roc = None
            ap = None
            baseline_brier = 1.0
            baseline_log_loss = 1.0
            reliability: list[dict[str, float | int]] = []
            confusion = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
            warnings.append("empty_evaluation_split")
        else:
            brier = float(math_utils.brier_score(model_probs, y_true))
            log_loss = float(math_utils.log_loss(model_probs, y_true))
            ece = float(math_utils.ece(model_probs, y_true))
            reliability = list(math_utils.reliability_bins(model_probs, y_true))
            baseline_brier = float(math_utils.brier_score(baseline_probs, y_true))
            baseline_log_loss = float(math_utils.log_loss(baseline_probs, y_true))
            if positive_count > 0 and negative_count > 0:
                roc = float(math_utils.roc_auc(model_probs, y_true))
                ap = float(math_utils.average_precision(model_probs, y_true))
            else:
                roc = None
                ap = None
                warnings.append("one_class_dataset")
            confusion = self._confusion(y_true, model_probs, threshold=0.5)

        cal_slope = payload.get("calibration_slope")
        cal_intercept = payload.get("calibration_intercept")
        try:
            cal_slope_f = float(cal_slope) if cal_slope is not None else None
            cal_intercept_f = float(cal_intercept) if cal_intercept is not None else None
        except (TypeError, ValueError):
            cal_slope_f = None
            cal_intercept_f = None

        passed_gates = self._validation_gates(
            model=model,
            manifest_sufficiency=bool(manifest.sufficiency_passed),
            y_true=y_true,
            model_probs=model_probs,
            brier=brier,
            ece=ece,
            baseline_brier=baseline_brier,
            warnings=warnings,
        )

        metrics_statistically_reliable = (
            row_count >= 30 and model.data_scope != PredictionDataScope.SYNTHETIC
        )
        if not metrics_statistically_reliable:
            warnings.append("metrics_not_statistically_reliable")

        evaluated_at = _utcnow()
        evaluation_id = build_entity_id(
            "pmev",
            ctx.tenant_id,
            model_id,
            split.value,
            model.parameter_hash[:16],
            str(int(evaluated_at.timestamp())),
        )
        evaluation = PredictionModelEvaluation(
            tenant_id=ctx.tenant_id,
            prediction_model_evaluation_id=evaluation_id,
            prediction_model_id=model_id,
            dataset_manifest_id=model.dataset_manifest_id,
            evaluation_split=split,
            evaluated_at=evaluated_at,
            row_count=row_count,
            positive_count=positive_count,
            negative_count=negative_count,
            brier_score=brier,
            log_loss=log_loss,
            roc_auc=roc,
            average_precision=ap,
            expected_calibration_error=ece,
            calibration_slope=cal_slope_f,
            calibration_intercept=cal_intercept_f,
            baseline_brier_score=baseline_brier,
            baseline_log_loss=baseline_log_loss,
            confusion_matrix=confusion,
            threshold_version=THRESHOLD_VERSION,
            reliability_bins=reliability,
            evaluation_warnings=warnings[:64],
            passed_validation_gates=passed_gates,
            metrics_statistically_reliable=metrics_statistically_reliable,
            created_at=evaluated_at,
        )
        self._uow.prediction_evaluations.insert(ctx, evaluation)
        logger.info(
            "prediction.model.evaluated tenant_id=%s model_id=%s split=%s "
            "brier=%.4f baseline_brier=%.4f gates=%s",
            ctx.tenant_id,
            model_id,
            split.value,
            brier,
            baseline_brier,
            passed_gates,
        )
        return evaluation

    def mark_validated(
        self,
        ctx: TenantContext,
        model_id: str,
        *,
        evaluation_id: str | None = None,
    ) -> PredictionModel:
        """Explicitly set candidate -> validated when gates passed.

        Does not promote to active.
        """
        model = self._uow.prediction_models.get(ctx, model_id)
        if model is None:
            raise LookupError(f"Prediction model not found: {model_id}")
        if model.model_state != ModelState.CANDIDATE:
            raise ValueError(
                f"Only candidate models can be validated; state={model.model_state.value}"
            )

        evaluation = None
        if evaluation_id:
            evaluation = self._uow.prediction_evaluations.get(ctx, evaluation_id)
        else:
            list_for_model = getattr(self._uow.prediction_evaluations, "list_for_model", None)
            if callable(list_for_model):
                evals = list(list_for_model(ctx, model_id))
                test_evals = [
                    e
                    for e in evals
                    if getattr(e.evaluation_split, "value", e.evaluation_split)
                    == EvaluationSplit.TEST.value
                ]
                evaluation = test_evals[0] if test_evals else (evals[0] if evals else None)

        if evaluation is None or not evaluation.passed_validation_gates:
            raise ValueError("Cannot validate model: missing evaluation or validation gates failed")

        model.model_state = ModelState.VALIDATED
        update = getattr(self._uow.prediction_models, "update", None)
        if callable(update):
            model = update(ctx, model)
        else:
            set_state = getattr(self._uow.prediction_models, "set_state", None)
            if callable(set_state):
                model = set_state(ctx, model_id, ModelState.VALIDATED)
            else:
                self._uow.prediction_models.insert(ctx, model)

        logger.info(
            "prediction.model.validated tenant_id=%s model_id=%s evaluation_id=%s",
            ctx.tenant_id,
            model_id,
            evaluation.prediction_model_evaluation_id,
        )
        return model

    def _validation_gates(
        self,
        *,
        model: PredictionModel,
        manifest_sufficiency: bool,
        y_true: list[int],
        model_probs: list[float],
        brier: float,
        ece: float,
        baseline_brier: float,
        warnings: list[str],
    ) -> bool:
        if not manifest_sufficiency:
            warnings.append("gate_fail_sufficiency")
            return False
        if not y_true or not (0 in y_true and 1 in y_true):
            warnings.append("gate_fail_both_classes")
            return False
        if any(not math.isfinite(p) or p < 0.0 or p > 1.0 for p in model_probs):
            warnings.append("gate_fail_probability_bounds")
            return False
        try:
            self._training_loader._assert_finite_parameters(model.parameter_payload)
        except ValueError:
            warnings.append("gate_fail_non_finite_parameters")
            return False

        coefs = [float(c) for c in model.parameter_payload.get("coefficients", [])]
        if any(abs(c) > 50.0 for c in coefs):
            warnings.append("gate_fail_coefficient_bounds")
            return False

        if brier > GATE_MAX_BRIER:
            warnings.append("gate_fail_brier")
            return False
        if ece > GATE_MAX_ECE:
            warnings.append("gate_fail_ece")
            return False
        if brier > baseline_brier + GATE_MAX_BASELINE_BRIER_DELTA:
            warnings.append("gate_fail_baseline_delta")
            return False

        expected_hash = model.parameter_hash
        from app.services.persistence.snapshot_service import snapshot_hash

        actual_hash = snapshot_hash(model.parameter_payload)
        if actual_hash != expected_hash:
            warnings.append("gate_fail_parameter_hash")
            return False

        return True

    @staticmethod
    def _confusion(y_true: list[int], probs: list[float], *, threshold: float) -> dict[str, int]:
        tp = tn = fp = fn = 0
        for label, prob in zip(y_true, probs, strict=True):
            pred = 1 if prob >= threshold else 0
            if pred == 1 and label == 1:
                tp += 1
            elif pred == 0 and label == 0:
                tn += 1
            elif pred == 1 and label == 0:
                fp += 1
            else:
                fn += 1
        return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}
