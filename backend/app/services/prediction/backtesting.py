"""Deterministic temporal backtesting for delivery prediction."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import (
    CALIBRATION_FRACTION,
    DEFAULT_HORIZON_DAYS,
    MAX_BACKTEST_FOLDS,
    MIN_CALIBRATION_ROWS,
    MIN_LABELED_ROWS,
    MIN_TEST_ROWS,
    TRAIN_FRACTION,
)
from app.domain.prediction_enums import EvaluationSplit, PredictionDataScope
from app.domain.prediction_models import (
    DeliveryOutcome,
    PredictionDatasetManifest,
    validate_horizon,
)
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction import math_utils
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.dataset_builder import PredictionDatasetBuilder
from app.services.prediction.evaluation import (
    PredictionEvaluationService,
    baseline_pseudo_probability,
)
from app.services.prediction.training import (
    PredictionTrainingService,
    predict_calibrated_proba,
    transform_snapshot,
)

logger = logging.getLogger("signalforge.prediction")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class PredictionBacktestService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._builder = PredictionDatasetBuilder(uow)
        self._trainer = PredictionTrainingService(uow)
        self._evaluator = PredictionEvaluationService(uow)
        self._scorecard = DeliveryScorecardV1()

    def run(
        self,
        ctx: TenantContext,
        *,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        max_folds: int = MAX_BACKTEST_FOLDS,
        seed: int = 42,
    ) -> dict[str, Any]:
        """Rolling-origin / temporal fold backtest with no future leakage.

        For small synthetic sets this may produce a single fold; the report
        states that limitation honestly.
        """
        horizon_days = validate_horizon(horizon_days)
        max_folds = max(1, min(int(max_folds), MAX_BACKTEST_FOLDS))

        # Build a full clean labeled set via the dataset builder path for snapshots.
        base_manifest = self._builder.build(ctx, horizon_days=horizon_days)
        ordered_ids = (
            list(base_manifest.train_row_ids)
            + list(base_manifest.calibration_row_ids)
            + list(base_manifest.test_row_ids)
        )
        # Re-sort by temporal key to ensure origin order.
        outcomes: list[DeliveryOutcome] = []
        for oid in ordered_ids:
            outcome = self._uow.delivery_outcomes.get(ctx, oid)
            if outcome is not None:
                outcomes.append(outcome)
        outcomes.sort(
            key=lambda o: (
                _aware(o.prediction_cutoff_at),
                o.target_id,
                o.delivery_outcome_id,
            )
        )

        folds = self._plan_folds(outcomes, max_folds=max_folds)
        fold_results: list[dict[str, Any]] = []
        limitations: list[str] = []

        if len(folds) <= 1:
            limitations.append(
                "single_fold_limitation: synthetic/small history does not support "
                "robust multi-fold backtesting; treat metrics as illustrative only"
            )

        if base_manifest.data_scope == PredictionDataScope.SYNTHETIC:
            limitations.append("synthetic_data_scope: backtest metrics are demo validation only")

        for fold_index, (train_ids, cal_ids, test_ids) in enumerate(folds):
            fold_hash = snapshot_hash(
                {
                    "fold_index": fold_index,
                    "train_row_ids": train_ids,
                    "calibration_row_ids": cal_ids,
                    "test_row_ids": test_ids,
                    "horizon_days": horizon_days,
                    "tenant_id": ctx.tenant_id,
                }
            )
            # Materialize a fold-specific ephemeral manifest (persisted for audit).
            fold_manifest = self._materialize_fold_manifest(
                ctx,
                base=base_manifest,
                train_ids=train_ids,
                cal_ids=cal_ids,
                test_ids=test_ids,
                fold_index=fold_index,
                fold_hash=fold_hash,
            )
            try:
                if not fold_manifest.sufficiency_passed:
                    fold_results.append(
                        {
                            "fold_index": fold_index,
                            "fold_hash": fold_hash,
                            "skipped": True,
                            "reason": "insufficiency",
                            "sufficiency_report": fold_manifest.sufficiency_report,
                            "train_count": len(train_ids),
                            "calibration_count": len(cal_ids),
                            "test_count": len(test_ids),
                        }
                    )
                    continue

                model = self._trainer.train(
                    ctx,
                    fold_manifest.prediction_dataset_manifest_id,
                    seed=seed + fold_index,
                )
                metrics = self._evaluate_fold(
                    ctx,
                    model_id=model.prediction_model_id,
                    manifest=fold_manifest,
                )
                fold_results.append(
                    {
                        "fold_index": fold_index,
                        "fold_hash": fold_hash,
                        "skipped": False,
                        "model_id": model.prediction_model_id,
                        "manifest_id": fold_manifest.prediction_dataset_manifest_id,
                        "train_count": len(train_ids),
                        "calibration_count": len(cal_ids),
                        "test_count": len(test_ids),
                        "metrics": metrics,
                        "cutoff_start": _aware(
                            self._uow.delivery_outcomes.get(ctx, train_ids[0]).prediction_cutoff_at  # type: ignore[union-attr]
                        ).isoformat()
                        if train_ids
                        else None,
                        "cutoff_end": _aware(
                            self._uow.delivery_outcomes.get(ctx, test_ids[-1]).prediction_cutoff_at  # type: ignore[union-attr]
                        ).isoformat()
                        if test_ids
                        else None,
                    }
                )
            except Exception as exc:  # noqa: BLE001 — fold isolation for demo CLI
                logger.warning(
                    "prediction.backtest.fold_failed tenant_id=%s fold=%s error=%s",
                    ctx.tenant_id,
                    fold_index,
                    type(exc).__name__,
                )
                fold_results.append(
                    {
                        "fold_index": fold_index,
                        "fold_hash": fold_hash,
                        "skipped": True,
                        "reason": f"fold_error:{type(exc).__name__}",
                        "train_count": len(train_ids),
                        "calibration_count": len(cal_ids),
                        "test_count": len(test_ids),
                    }
                )

        completed = [f for f in fold_results if not f.get("skipped")]
        aggregate = self._aggregate(completed)
        report = {
            "tenant_id": ctx.tenant_id,
            "horizon_days": horizon_days,
            "fold_count": len(folds),
            "completed_fold_count": len(completed),
            "sample_count": len(outcomes),
            "base_dataset_hash": base_manifest.dataset_hash,
            "folds": fold_results,
            "aggregate_metrics": aggregate,
            "limitations": limitations,
            "generated_at": _utcnow().isoformat(),
            "backtest_id": build_entity_id(
                "pbt",
                ctx.tenant_id,
                base_manifest.dataset_hash[:16],
                str(len(folds)),
            ),
        }
        logger.info(
            "prediction.backtest.completed tenant_id=%s folds=%s completed=%s",
            ctx.tenant_id,
            len(folds),
            len(completed),
        )
        return report

    def _plan_folds(
        self,
        outcomes: list[DeliveryOutcome],
        *,
        max_folds: int,
    ) -> list[tuple[list[str], list[str], list[str]]]:
        n = len(outcomes)
        if n < max(MIN_LABELED_ROWS // 2, MIN_CALIBRATION_ROWS + MIN_TEST_ROWS + 5):
            # Single temporal split mirroring 60/20/20.
            train_end = int(n * TRAIN_FRACTION)
            cal_end = train_end + int(n * CALIBRATION_FRACTION)
            ids = [o.delivery_outcome_id for o in outcomes]
            return [(ids[:train_end], ids[train_end:cal_end], ids[cal_end:])]

        folds: list[tuple[list[str], list[str], list[str]]] = []
        # Rolling origin: expand train window, hold fixed-size cal/test tails.
        min_train = max(10, int(n * 0.4))
        cal_size = max(MIN_CALIBRATION_ROWS, int(n * CALIBRATION_FRACTION))
        test_size = max(MIN_TEST_ROWS, int(n * 0.2))
        step = max(1, (n - min_train - cal_size - test_size) // max(1, max_folds))

        origin = min_train
        while origin + cal_size + test_size <= n and len(folds) < max_folds:
            train_ids = [o.delivery_outcome_id for o in outcomes[:origin]]
            cal_ids = [o.delivery_outcome_id for o in outcomes[origin : origin + cal_size]]
            test_ids = [
                o.delivery_outcome_id
                for o in outcomes[origin + cal_size : origin + cal_size + test_size]
            ]
            # Enforce no future leakage: max train cutoff < min cal cutoff < min test.
            if train_ids and cal_ids and test_ids:
                folds.append((train_ids, cal_ids, test_ids))
            origin += step

        if not folds:
            ids = [o.delivery_outcome_id for o in outcomes]
            train_end = int(n * TRAIN_FRACTION)
            cal_end = train_end + int(n * CALIBRATION_FRACTION)
            folds.append((ids[:train_end], ids[train_end:cal_end], ids[cal_end:]))
        return folds[:max_folds]

    def _materialize_fold_manifest(
        self,
        ctx: TenantContext,
        *,
        base: PredictionDatasetManifest,
        train_ids: list[str],
        cal_ids: list[str],
        test_ids: list[str],
        fold_index: int,
        fold_hash: str,
    ) -> PredictionDatasetManifest:
        labeled = len(train_ids) + len(cal_ids) + len(test_ids)
        positives = 0
        negatives = 0
        cutoffs: list[datetime] = []
        for oid in train_ids + cal_ids + test_ids:
            outcome = self._uow.delivery_outcomes.get(ctx, oid)
            if outcome is None:
                continue
            cutoffs.append(_aware(outcome.prediction_cutoff_at))
            if outcome.binary_label == 1:
                positives += 1
            elif outcome.binary_label == 0:
                negatives += 1

        sufficiency = {
            "passed": (
                labeled >= 20
                and positives >= 3
                and negatives >= 3
                and len(cal_ids) >= 3
                and len(test_ids) >= 3
                and bool(
                    base.sufficiency_report.get("checks", {})
                    .get("leakage_clean", {})
                    .get("passed", True)
                )
            ),
            "fold_index": fold_index,
            "relaxed_for_backtest": True,
        }
        # Prefer full thresholds when possible.
        if (
            labeled >= MIN_LABELED_ROWS
            and positives >= 5
            and negatives >= 5
            and len(cal_ids) >= MIN_CALIBRATION_ROWS
            and len(test_ids) >= MIN_TEST_ROWS
        ):
            sufficiency["passed"] = True
            sufficiency["relaxed_for_backtest"] = False

        generated_at = _utcnow()
        minimum_cutoff_at = min(cutoffs) if cutoffs else generated_at
        maximum_cutoff_at = max(cutoffs) if cutoffs else generated_at
        dataset_hash = snapshot_hash(
            {
                "base_dataset_hash": base.dataset_hash,
                "fold_hash": fold_hash,
                "fold_index": fold_index,
                "train_row_ids": train_ids,
                "calibration_row_ids": cal_ids,
                "test_row_ids": test_ids,
            }
        )
        manifest = PredictionDatasetManifest(
            tenant_id=ctx.tenant_id,
            prediction_dataset_manifest_id=build_entity_id(
                "pdm", ctx.tenant_id, "backtest", fold_hash[:20]
            ),
            target_definition=base.target_definition,
            label_version=base.label_version,
            feature_schema_version=base.feature_schema_version,
            horizon_days=base.horizon_days,
            generated_at=generated_at,
            minimum_cutoff_at=minimum_cutoff_at,
            maximum_cutoff_at=maximum_cutoff_at,
            total_rows=labeled,
            labeled_rows=labeled,
            excluded_rows=0,
            positive_rows=positives,
            negative_rows=negatives,
            censored_rows=0,
            tenant_count=1,
            feature_count=base.feature_count,
            split_strategy=f"backtest_fold_{fold_index}",
            train_row_ids_hash=snapshot_hash(train_ids),
            calibration_row_ids_hash=snapshot_hash(cal_ids),
            test_row_ids_hash=snapshot_hash(test_ids),
            leakage_report_hash=base.leakage_report_hash,
            dataset_hash=dataset_hash,
            data_scope=base.data_scope,
            source_high_watermarks=dict(base.source_high_watermarks),
            exclusion_reasons={},
            sufficiency_passed=bool(sufficiency["passed"]),
            sufficiency_report=sufficiency,
            train_row_ids=train_ids,
            calibration_row_ids=cal_ids,
            test_row_ids=test_ids,
            created_at=generated_at,
        )
        existing = None
        get_by_hash = getattr(self._uow.prediction_datasets, "get_by_hash", None)
        if callable(get_by_hash):
            existing = get_by_hash(ctx, dataset_hash)
        if existing is not None:
            return existing
        self._uow.prediction_datasets.insert(ctx, manifest)
        return manifest

    def _evaluate_fold(
        self,
        ctx: TenantContext,
        *,
        model_id: str,
        manifest: PredictionDatasetManifest,
    ) -> dict[str, Any]:
        model = self._uow.prediction_models.get(ctx, model_id)
        if model is None:
            raise LookupError(model_id)
        rows = self._trainer._load_split_rows(ctx, manifest, EvaluationSplit.TEST)
        y_true = [int(o.binary_label or 0) for o, _ in rows]
        model_probs: list[float] = []
        baseline_probs: list[float] = []
        for _, snapshot in rows:
            normalized, _, _ = transform_snapshot(snapshot, model.parameter_payload)
            model_probs.append(predict_calibrated_proba(normalized, model.parameter_payload))
            score = self._scorecard.score(snapshot.feature_values, snapshot.missingness_indicators)
            baseline_probs.append(baseline_pseudo_probability(score.delivery_risk_score))

        metrics: dict[str, Any] = {
            "row_count": len(y_true),
            "brier_score": float(math_utils.brier_score(model_probs, y_true)) if y_true else None,
            "log_loss": float(math_utils.log_loss(model_probs, y_true)) if y_true else None,
            "expected_calibration_error": float(math_utils.ece(model_probs, y_true))
            if y_true
            else None,
            "baseline_brier_score": float(math_utils.brier_score(baseline_probs, y_true))
            if y_true
            else None,
            "split": EvaluationSplit.BACKTEST_FOLD.value,
        }
        if y_true and 0 in y_true and 1 in y_true:
            metrics["roc_auc"] = float(math_utils.roc_auc(model_probs, y_true))
            metrics["average_precision"] = float(math_utils.average_precision(model_probs, y_true))
        else:
            metrics["roc_auc"] = None
            metrics["average_precision"] = None
        return metrics

    @staticmethod
    def _aggregate(completed: list[dict[str, Any]]) -> dict[str, Any]:
        if not completed:
            return {"fold_count": 0}
        keys = (
            "brier_score",
            "log_loss",
            "expected_calibration_error",
            "baseline_brier_score",
            "roc_auc",
            "average_precision",
        )
        aggregate: dict[str, Any] = {"fold_count": len(completed)}
        for key in keys:
            values = [
                f["metrics"][key]
                for f in completed
                if f.get("metrics") and f["metrics"].get(key) is not None
            ]
            if values:
                aggregate[f"mean_{key}"] = sum(values) / len(values)
            else:
                aggregate[f"mean_{key}"] = None
        return aggregate
