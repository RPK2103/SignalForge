"""Regularized logistic training with train-only imputation/scaling and Platt fit."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import (
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    L2_REGULARIZATION,
    LABEL_VERSION,
    LEARNING_RATE,
    MAX_TRAINING_ITERATIONS,
    MODEL_NAME,
    MODEL_TYPE,
    TARGET_DEFINITION,
    THRESHOLD_VERSION,
    TRAINING_CODE_VERSION,
    TRAINING_SEED,
)
from app.domain.prediction_enums import (
    EvaluationSplit,
    ModelState,
    ModelUsageScope,
    PredictionDataScope,
)
from app.domain.prediction_models import (
    DeliveryOutcome,
    PredictionDatasetManifest,
    PredictionFeatureSnapshot,
    PredictionModel,
)
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction import math_utils
from app.services.prediction.calibration import fit_platt_calibrator
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.prediction.feature_schema import FEATURE_NAMES, feature_schema_hash

logger = logging.getLogger("signalforge.prediction")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_feature_list() -> list[str]:
    """Ordered model features: schema features + per-feature missingness flags."""
    return list(FEATURE_NAMES) + [f"{name}__missing" for name in FEATURE_NAMES]


def extract_raw_and_missing(
    snapshot: PredictionFeatureSnapshot,
    feature_list: list[str] | None = None,
) -> tuple[list[float | None], list[bool]]:
    names = feature_list or build_feature_list()
    raw: list[float | None] = []
    imputed_flags: list[bool] = []
    base = set(FEATURE_NAMES)
    for name in names:
        if name.endswith("__missing"):
            base_name = name[: -len("__missing")]
            flag = int(snapshot.missingness_indicators.get(base_name, 0))
            if flag == 0 and snapshot.feature_values.get(base_name) is None:
                flag = 1
            raw.append(float(flag))
            imputed_flags.append(False)
            continue
        if name not in base and name not in snapshot.feature_values:
            raw.append(None)
            imputed_flags.append(True)
            continue
        value = snapshot.feature_values.get(name)
        if value is None:
            raw.append(None)
            imputed_flags.append(True)
        else:
            raw.append(float(value))
            imputed_flags.append(False)
    return raw, imputed_flags


def fit_imputer(matrix: list[list[float | None]]) -> list[float]:
    if not matrix:
        return []
    n_features = len(matrix[0])
    means: list[float] = []
    for j in range(n_features):
        vals = [row[j] for row in matrix if row[j] is not None]
        means.append(math_utils.mean(vals) if vals else 0.0)
    return means


def apply_imputer(
    row: list[float | None], impute_values: list[float]
) -> tuple[list[float], list[bool]]:
    out: list[float] = []
    was_imputed: list[bool] = []
    for idx, value in enumerate(row):
        if value is None:
            fill = float(impute_values[idx]) if idx < len(impute_values) else 0.0
            out.append(fill)
            was_imputed.append(True)
        else:
            out.append(float(value))
            was_imputed.append(False)
    return out, was_imputed


def fit_scaler(matrix: list[list[float]]) -> tuple[list[float], list[float]]:
    if not matrix:
        return [], []
    n_features = len(matrix[0])
    means: list[float] = []
    stds: list[float] = []
    for j in range(n_features):
        col = [row[j] for row in matrix]
        means.append(math_utils.mean(col))
        s = math_utils.std(col)
        stds.append(s if s > 1e-12 else 1.0)
    return means, stds


def apply_scaler(row: list[float], means: list[float], stds: list[float]) -> list[float]:
    out: list[float] = []
    for idx, value in enumerate(row):
        mean = means[idx] if idx < len(means) else 0.0
        std = stds[idx] if idx < len(stds) else 1.0
        if std <= 1e-12:
            std = 1.0
        out.append((float(value) - mean) / std)
    return out


def transform_snapshot(
    snapshot: PredictionFeatureSnapshot,
    parameter_payload: dict[str, Any],
) -> tuple[list[float], list[float | None], list[bool]]:
    """Impute + scale a snapshot using stored training parameters."""
    feature_list = list(parameter_payload["feature_list"])
    impute_values = [float(v) for v in parameter_payload["impute_values"]]
    scale_means = [float(v) for v in parameter_payload["scale_means"]]
    scale_stds = [float(v) for v in parameter_payload["scale_stds"]]
    raw, _ = extract_raw_and_missing(snapshot, feature_list)
    imputed, was_imputed = apply_imputer(raw, impute_values)
    normalized = apply_scaler(imputed, scale_means, scale_stds)
    return normalized, raw, was_imputed


def predict_raw_proba(
    normalized_row: list[float],
    parameter_payload: dict[str, Any],
) -> float:
    coef = [float(c) for c in parameter_payload["coefficients"]]
    intercept = float(parameter_payload["intercept"])
    probs = math_utils.predict_proba([normalized_row], coef, intercept)
    return float(probs[0])


def predict_calibrated_proba(
    normalized_row: list[float],
    parameter_payload: dict[str, Any],
) -> float:
    from app.services.prediction.calibration import apply_platt_calibrator

    raw_p = predict_raw_proba(normalized_row, parameter_payload)
    slope = float(parameter_payload["calibration_slope"])
    intercept = float(parameter_payload["calibration_intercept"])
    calibrated = apply_platt_calibrator(raw_p, slope, intercept)
    return float(calibrated)


class PredictionTrainingService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def train(
        self,
        ctx: TenantContext,
        manifest_id: str,
        seed: int = TRAINING_SEED,
    ) -> PredictionModel:
        manifest = self._uow.prediction_datasets.get(ctx, manifest_id)
        if manifest is None:
            raise LookupError(f"Dataset manifest not found: {manifest_id}")

        if not manifest.sufficiency_passed:
            raise ValueError(
                "Cannot train: dataset sufficiency thresholds not met. "
                f"report={manifest.sufficiency_report}"
            )

        leakage_clean = self._manifest_leakage_clean(manifest)
        if not leakage_clean:
            raise ValueError("Cannot train: leakage report is not clean for this dataset manifest")

        train_rows = self._load_split_rows(ctx, manifest, EvaluationSplit.TRAIN)
        cal_rows = self._load_split_rows(ctx, manifest, EvaluationSplit.CALIBRATION)
        if not train_rows:
            raise ValueError("Cannot train: empty training partition")

        feature_list = build_feature_list()
        train_raw = [extract_raw_and_missing(snap, feature_list)[0] for _, snap in train_rows]
        impute_values = fit_imputer(train_raw)
        train_imputed = [apply_imputer(row, impute_values)[0] for row in train_raw]
        scale_means, scale_stds = fit_scaler(train_imputed)
        train_x = [apply_scaler(row, scale_means, scale_stds) for row in train_imputed]
        train_y = [int(outcome.binary_label or 0) for outcome, _ in train_rows]

        coefficients, intercept = math_utils.fit_logistic_l2(
            train_x,
            train_y,
            seed=seed,
            l2=L2_REGULARIZATION,
            max_iter=MAX_TRAINING_ITERATIONS,
            lr=LEARNING_RATE,
        )

        # Platt on calibration partition only.
        if cal_rows:
            cal_raw = [extract_raw_and_missing(snap, feature_list)[0] for _, snap in cal_rows]
            cal_imputed = [apply_imputer(row, impute_values)[0] for row in cal_raw]
            cal_x = [apply_scaler(row, scale_means, scale_stds) for row in cal_imputed]
            cal_y = [int(outcome.binary_label or 0) for outcome, _ in cal_rows]
            cal_uncal = [float(p) for p in math_utils.predict_proba(cal_x, coefficients, intercept)]
            try:
                cal_slope, cal_intercept = fit_platt_calibrator(cal_uncal, cal_y)
            except ValueError:
                cal_slope, cal_intercept = 1.0, 0.0
        else:
            cal_slope, cal_intercept = 1.0, 0.0

        train_positive_rate = sum(train_y) / len(train_y) if train_y else 0.0
        feature_ranges = self._compute_feature_ranges(train_rows, feature_list)
        train_missing_rates = self._compute_missing_rates(train_rows, feature_list)

        schema_hash = feature_schema_hash()
        parameter_payload: dict[str, Any] = {
            "feature_list": feature_list,
            "impute_values": [float(v) for v in impute_values],
            "scale_means": [float(v) for v in scale_means],
            "scale_stds": [float(v) for v in scale_stds],
            "coefficients": [float(c) for c in coefficients],
            "intercept": float(intercept),
            "calibration_slope": float(cal_slope),
            "calibration_intercept": float(cal_intercept),
            "threshold_version": THRESHOLD_VERSION,
            "feature_schema_hash": schema_hash,
            "training_dataset_hash": manifest.dataset_hash,
            "train_positive_rate": float(train_positive_rate),
            "feature_ranges": feature_ranges,
            "train_missing_rates": train_missing_rates,
            "model_name": MODEL_NAME,
            "model_type": MODEL_TYPE,
        }
        self._assert_finite_parameters(parameter_payload)
        parameter_hash = snapshot_hash(parameter_payload)

        data_scope = manifest.data_scope
        usage_scope = (
            ModelUsageScope.DEMO
            if data_scope == PredictionDataScope.SYNTHETIC
            else ModelUsageScope.EVALUATION
        )
        production_eligible = False
        if data_scope == PredictionDataScope.SYNTHETIC:
            production_eligible = False
            usage_scope = ModelUsageScope.DEMO

        trained_at = _utcnow()
        model_version = f"v1-{parameter_hash[:12]}"
        model_id = build_entity_id(
            "pmod",
            ctx.tenant_id,
            MODEL_NAME,
            str(manifest.horizon_days),
            parameter_hash[:24],
        )

        model = PredictionModel(
            tenant_id=ctx.tenant_id,
            prediction_model_id=model_id,
            model_name=MODEL_NAME,
            model_type=MODEL_TYPE,
            model_version=model_version,
            target_definition=TARGET_DEFINITION,
            horizon_days=manifest.horizon_days or DEFAULT_HORIZON_DAYS,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            label_version=LABEL_VERSION,
            dataset_manifest_id=manifest.prediction_dataset_manifest_id,
            training_code_version=TRAINING_CODE_VERSION,
            parameter_payload=parameter_payload,
            parameter_hash=parameter_hash,
            training_seed=int(seed),
            trained_at=trained_at,
            model_state=ModelState.CANDIDATE,
            usage_scope=usage_scope,
            data_scope=data_scope,
            production_eligible=production_eligible,
            promoted_at=None,
            retired_at=None,
            created_at=trained_at,
        )
        self._uow.prediction_models.insert(ctx, model)
        logger.info(
            "prediction.model.trained tenant_id=%s model_id=%s manifest_id=%s "
            "state=candidate production_eligible=%s",
            ctx.tenant_id,
            model_id,
            manifest_id,
            production_eligible,
        )
        # Explicitly do not auto-promote.
        return model

    def _manifest_leakage_clean(self, manifest: PredictionDatasetManifest) -> bool:
        report = manifest.sufficiency_report or {}
        checks = report.get("checks") if isinstance(report, dict) else None
        if isinstance(checks, dict) and "leakage_clean" in checks:
            return bool(checks["leakage_clean"].get("passed", False))
        # Refuse training when sufficiency never recorded an explicit leakage
        # check — do not treat a prebuilt/partial manifest as clean by default.
        if manifest.exclusion_reasons.get("leakage_rejected", 0) > 0:
            return False
        return False

    def _load_split_rows(
        self,
        ctx: TenantContext,
        manifest: PredictionDatasetManifest,
        split: EvaluationSplit,
    ) -> list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]]:
        if split == EvaluationSplit.TRAIN:
            row_ids = list(manifest.train_row_ids)
        elif split == EvaluationSplit.CALIBRATION:
            row_ids = list(manifest.calibration_row_ids)
        else:
            row_ids = list(manifest.test_row_ids)

        rows: list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]] = []
        for outcome_id in row_ids:
            outcome = self._uow.delivery_outcomes.get(ctx, outcome_id)
            if outcome is None:
                raise LookupError(f"Missing delivery outcome {outcome_id}")
            snapshot = None
            get_or_none = getattr(self._uow.prediction_feature_snapshots, "get_or_none", None)
            if callable(get_or_none):
                snapshot = get_or_none(
                    ctx,
                    target_type=outcome.target_type.value
                    if hasattr(outcome.target_type, "value")
                    else str(outcome.target_type),
                    target_id=outcome.target_id,
                    as_of_at=outcome.prediction_cutoff_at,
                    horizon_days=outcome.horizon_days,
                    feature_schema_version=FEATURE_SCHEMA_VERSION,
                )
            if snapshot is None:
                snapshot = FeatureExtractor(self._uow).extract(
                    ctx,
                    outcome.target_type,
                    outcome.target_id,
                    outcome.prediction_cutoff_at,
                    horizon_days=outcome.horizon_days,
                    data_scope=outcome.data_scope,
                )
            rows.append((outcome, snapshot))
        return rows

    @staticmethod
    def _compute_feature_ranges(
        rows: list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]],
        feature_list: list[str],
    ) -> dict[str, dict[str, float]]:
        ranges: dict[str, dict[str, float]] = {}
        for name in feature_list:
            if name.endswith("__missing"):
                continue
            vals: list[float] = []
            for _, snap in rows:
                value = snap.feature_values.get(name)
                if value is not None:
                    vals.append(float(value))
            if vals:
                ranges[name] = {"min": min(vals), "max": max(vals)}
        return ranges

    @staticmethod
    def _compute_missing_rates(
        rows: list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]],
        feature_list: list[str],
    ) -> dict[str, float]:
        if not rows:
            return {}
        rates: dict[str, float] = {}
        n = len(rows)
        for name in feature_list:
            if name.endswith("__missing"):
                continue
            missing = 0
            for _, snap in rows:
                flag = int(snap.missingness_indicators.get(name, 0))
                if flag == 1 or snap.feature_values.get(name) is None:
                    missing += 1
            rates[name] = missing / n
        return rates

    @staticmethod
    def _assert_finite_parameters(payload: dict[str, Any]) -> None:
        for key in (
            "impute_values",
            "scale_means",
            "scale_stds",
            "coefficients",
        ):
            for value in payload[key]:
                if not math.isfinite(float(value)):
                    raise ValueError(f"Non-finite value in {key}")
        for key in ("intercept", "calibration_slope", "calibration_intercept"):
            if not math.isfinite(float(payload[key])):
                raise ValueError(f"Non-finite value in {key}")
