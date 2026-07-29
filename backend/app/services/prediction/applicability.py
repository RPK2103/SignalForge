"""Out-of-distribution and data-sufficiency checks for delivery predictions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domain.prediction_constants import (
    MAX_DATA_QUALITY_WARNINGS,
    SUPPORTED_HORIZONS,
)
from app.domain.prediction_enums import (
    ApplicabilityStatus,
    PredictionDataQualityWarning,
    PredictionDataScope,
    ReliabilityStatus,
)
from app.domain.prediction_models import PredictionFeatureSnapshot, PredictionModel


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def check_applicability(
    *,
    snapshot: PredictionFeatureSnapshot,
    model: PredictionModel | None,
    horizon_days: int,
    training_ranges: dict[str, dict[str, float]] | None = None,
    train_missing_rates: dict[str, float] | None = None,
    target_resolved: bool = True,
    evidence_stale_hours: float | None = None,
    stale_threshold_hours: float = 168.0,
    critical_missing_features: list[str] | None = None,
) -> tuple[ApplicabilityStatus, ReliabilityStatus, list[str]]:
    """Compare inference features against training metadata and return warnings.

    This is a basic applicability check — not a full statistical drift platform.
    """
    warnings: list[str] = []

    if horizon_days not in SUPPORTED_HORIZONS:
        warnings.append(PredictionDataQualityWarning.UNSUPPORTED_HORIZON.value)

    if not target_resolved:
        warnings.append(PredictionDataQualityWarning.UNRESOLVED_TARGET.value)

    if critical_missing_features:
        warnings.append(PredictionDataQualityWarning.HIGH_MISSINGNESS.value)

    for raw in snapshot.data_quality_warnings:
        token = str(raw)
        if token not in warnings:
            warnings.append(token)

    if model is None:
        warnings.append(PredictionDataQualityWarning.MODEL_NOT_VALIDATED.value)
        warnings.append(PredictionDataQualityWarning.BASELINE_FALLBACK.value)
    else:
        if model.data_scope == PredictionDataScope.SYNTHETIC:
            warnings.append(PredictionDataQualityWarning.SYNTHETIC_MODEL.value)

        if model.model_state.value not in {"active", "validated"}:
            warnings.append(PredictionDataQualityWarning.MODEL_NOT_VALIDATED.value)

    ranges = training_ranges or {}
    for name, value in snapshot.feature_values.items():
        if value is None:
            continue
        bounds = ranges.get(name)
        if not bounds:
            continue
        lo = bounds.get("min")
        hi = bounds.get("max")
        if lo is not None and value < lo:
            warnings.append(PredictionDataQualityWarning.FEATURE_OUTSIDE_TRAINING_RANGE.value)
            break
        if hi is not None and value > hi:
            warnings.append(PredictionDataQualityWarning.FEATURE_OUTSIDE_TRAINING_RANGE.value)
            break

    missing_rates = train_missing_rates or {}
    elevated = False
    for name, flag in snapshot.missingness_indicators.items():
        if int(flag) != 1:
            continue
        train_rate = missing_rates.get(name, 0.0)
        if train_rate < 0.5:
            elevated = True
            break
    if elevated:
        token = PredictionDataQualityWarning.HIGH_MISSINGNESS.value
        if token not in warnings:
            warnings.append(token)

    if evidence_stale_hours is not None and evidence_stale_hours > stale_threshold_hours:
        warnings.append(PredictionDataQualityWarning.STALE_EVIDENCE.value)

    as_of = _aware(snapshot.as_of_at)
    evidence_cutoff = _aware(snapshot.evidence_cutoff_at)
    if as_of and evidence_cutoff:
        age_hours = (as_of - evidence_cutoff).total_seconds() / 3600.0
        if age_hours > stale_threshold_hours:
            token = PredictionDataQualityWarning.STALE_EVIDENCE.value
            if token not in warnings:
                warnings.append(token)

    graph_warnings = {
        PredictionDataQualityWarning.GRAPH_NOT_CURRENT.value,
        PredictionDataQualityWarning.GRAPH_UNAVAILABLE.value,
    }
    if graph_warnings.intersection(warnings):
        pass

    # Deduplicate while preserving order; bound length.
    deduped: list[str] = []
    seen: set[str] = set()
    for item in warnings:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
        if len(deduped) >= MAX_DATA_QUALITY_WARNINGS:
            break

    blocking = {
        PredictionDataQualityWarning.UNRESOLVED_TARGET.value,
        PredictionDataQualityWarning.UNSUPPORTED_HORIZON.value,
        PredictionDataQualityWarning.INSUFFICIENT_HISTORY.value,
    }
    degraded_tokens = {
        PredictionDataQualityWarning.FEATURE_OUTSIDE_TRAINING_RANGE.value,
        PredictionDataQualityWarning.HIGH_MISSINGNESS.value,
        PredictionDataQualityWarning.STALE_EVIDENCE.value,
        PredictionDataQualityWarning.GRAPH_NOT_CURRENT.value,
        PredictionDataQualityWarning.GRAPH_UNAVAILABLE.value,
        PredictionDataQualityWarning.SYNTHETIC_MODEL.value,
        PredictionDataQualityWarning.MODEL_NOT_VALIDATED.value,
        PredictionDataQualityWarning.BASELINE_FALLBACK.value,
        PredictionDataQualityWarning.STALE_SOURCE.value,
        PredictionDataQualityWarning.INCOMPLETE_HISTORY.value,
        PredictionDataQualityWarning.MISSING_OWNER.value,
    }

    if blocking.intersection(deduped) or critical_missing_features:
        applicability = ApplicabilityStatus.NOT_APPLICABLE
    elif degraded_tokens.intersection(deduped):
        applicability = ApplicabilityStatus.DEGRADED
    else:
        applicability = ApplicabilityStatus.APPLICABLE

    reliability = _reliability_from_warnings(deduped, model=model)
    return applicability, reliability, deduped


def _reliability_from_warnings(
    warnings: list[str],
    *,
    model: PredictionModel | None,
) -> ReliabilityStatus:
    warning_set = set(warnings)
    if PredictionDataQualityWarning.UNRESOLVED_TARGET.value in warning_set:
        return ReliabilityStatus.INSUFFICIENT_HISTORY
    if PredictionDataQualityWarning.INSUFFICIENT_HISTORY.value in warning_set:
        return ReliabilityStatus.INSUFFICIENT_HISTORY
    if PredictionDataQualityWarning.FEATURE_OUTSIDE_TRAINING_RANGE.value in warning_set:
        return ReliabilityStatus.OUT_OF_DISTRIBUTION
    if PredictionDataQualityWarning.STALE_EVIDENCE.value in warning_set:
        return ReliabilityStatus.STALE_DATA
    if model is None:
        return ReliabilityStatus.MODEL_UNAVAILABLE
    from app.domain.prediction_enums import ModelState

    if model.model_state == ModelState.ACTIVE and model.production_eligible:
        return ReliabilityStatus.VALIDATED
    if model.model_state == ModelState.ACTIVE:
        return ReliabilityStatus.LIMITED
    return ReliabilityStatus.MODEL_UNAVAILABLE


def training_feature_ranges(parameter_payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Extract optional per-feature training min/max from parameter payload."""
    raw = parameter_payload.get("feature_ranges") or {}
    result: dict[str, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return result
    for name, bounds in raw.items():
        if not isinstance(bounds, dict):
            continue
        entry: dict[str, float] = {}
        if "min" in bounds and bounds["min"] is not None:
            entry["min"] = float(bounds["min"])
        if "max" in bounds and bounds["max"] is not None:
            entry["max"] = float(bounds["max"])
        if entry:
            result[str(name)] = entry
    return result


def training_missing_rates(parameter_payload: dict[str, Any]) -> dict[str, float]:
    raw = parameter_payload.get("train_missing_rates") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items()}
