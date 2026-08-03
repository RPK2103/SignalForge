"""Prediction calibration & drift snapshots (Phase 3 Prompt 8).

Reuses Prompt 4 prediction artifacts; NEVER retrains a model. Produces honest,
immutable snapshots:

- no labels                -> calibration ``unavailable`` (not zero);
- fewer than the minimum   -> ``insufficient_data``;
- an uncalibrated score    -> never reported as a probability;
- drift is only reported when mathematically supported (PSI on a stable
  binned distribution), otherwise ``drift_method=None``.

All calculations are deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

MIN_CALIBRATION_SAMPLES = 20
MIN_DRIFT_SAMPLES = 20
_EPSILON = 1e-6


class PredictionQualityStatus(str, Enum):
    AVAILABLE = "available"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    n = len(probabilities)
    if n == 0 or n != len(outcomes):
        raise ValueError("probabilities and outcomes must be non-empty and equal length")
    return sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / n


def expected_calibration_error(
    probabilities: Sequence[float], outcomes: Sequence[int], *, bins: int = 10
) -> float:
    n = len(probabilities)
    if n == 0:
        raise ValueError("probabilities must be non-empty")
    bin_totals = [0] * bins
    bin_conf = [0.0] * bins
    bin_acc = [0.0] * bins
    for p, y in zip(probabilities, outcomes):
        idx = min(int(p * bins), bins - 1)
        bin_totals[idx] += 1
        bin_conf[idx] += p
        bin_acc[idx] += y
    ece = 0.0
    for i in range(bins):
        if bin_totals[i] == 0:
            continue
        conf = bin_conf[i] / bin_totals[i]
        acc = bin_acc[i] / bin_totals[i]
        ece += (bin_totals[i] / n) * abs(acc - conf)
    return ece


def _binned_distribution(values: Sequence[float], edges: Sequence[float]) -> list[float]:
    counts = [0] * (len(edges) - 1)
    for value in values:
        placed = False
        for i in range(len(edges) - 1):
            if edges[i] <= value < edges[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed and value >= edges[-1]:
            counts[-1] += 1
    total = sum(counts) or 1
    return [c / total for c in counts]


def population_stability_index(
    baseline: Sequence[float], current: Sequence[float], *, bins: int = 10
) -> float:
    """PSI between two same-scale numeric distributions (0..1 assumed)."""
    edges = [i / bins for i in range(bins + 1)]
    base = _binned_distribution(baseline, edges)
    curr = _binned_distribution(current, edges)
    psi = 0.0
    for b, c in zip(base, curr):
        b_adj = max(b, _EPSILON)
        c_adj = max(c, _EPSILON)
        psi += (c_adj - b_adj) * math.log(c_adj / b_adj)
    return psi


@dataclass(frozen=True, slots=True)
class CalibrationSnapshot:
    status: PredictionQualityStatus
    brier_score: float | None
    calibration_error: float | None
    label_coverage: float | None
    sample_count: int
    prediction_distribution: list[float] = field(default_factory=list)
    outcome_distribution: list[float] = field(default_factory=list)


def build_calibration_snapshot(
    *,
    probabilities: Sequence[float | None],
    outcomes: Sequence[int | None],
    min_samples: int = MIN_CALIBRATION_SAMPLES,
) -> CalibrationSnapshot:
    total = len(probabilities)
    labeled = [
        (float(p), int(y))
        for p, y in zip(probabilities, outcomes)
        if p is not None and y is not None
    ]
    label_coverage = (len(labeled) / total) if total else None

    if not labeled:
        # No labels available -> calibration UNAVAILABLE, not zero.
        return CalibrationSnapshot(
            status=PredictionQualityStatus.UNAVAILABLE,
            brier_score=None,
            calibration_error=None,
            label_coverage=label_coverage,
            sample_count=len(labeled),
        )
    if len(labeled) < min_samples:
        return CalibrationSnapshot(
            status=PredictionQualityStatus.INSUFFICIENT_DATA,
            brier_score=None,
            calibration_error=None,
            label_coverage=label_coverage,
            sample_count=len(labeled),
        )
    probs = [p for p, _ in labeled]
    ys = [y for _, y in labeled]
    edges = [i / 10 for i in range(11)]
    return CalibrationSnapshot(
        status=PredictionQualityStatus.AVAILABLE,
        brier_score=brier_score(probs, ys),
        calibration_error=expected_calibration_error(probs, ys),
        label_coverage=label_coverage,
        sample_count=len(labeled),
        prediction_distribution=_binned_distribution(probs, edges),
        outcome_distribution=[1 - (sum(ys) / len(ys)), sum(ys) / len(ys)],
    )


@dataclass(frozen=True, slots=True)
class DriftSnapshot:
    status: PredictionQualityStatus
    drift_score: float | None
    drift_method: str | None
    sample_count: int
    baseline_distribution: list[float] = field(default_factory=list)
    current_distribution: list[float] = field(default_factory=list)


def build_drift_snapshot(
    *,
    baseline: Sequence[float],
    current: Sequence[float],
    min_samples: int = MIN_DRIFT_SAMPLES,
) -> DriftSnapshot:
    if not baseline or not current:
        return DriftSnapshot(
            status=PredictionQualityStatus.UNAVAILABLE,
            drift_score=None,
            drift_method=None,
            sample_count=len(current),
        )
    if len(current) < min_samples or len(baseline) < min_samples:
        return DriftSnapshot(
            status=PredictionQualityStatus.INSUFFICIENT_DATA,
            drift_score=None,
            drift_method=None,
            sample_count=len(current),
        )
    edges = [i / 10 for i in range(11)]
    return DriftSnapshot(
        status=PredictionQualityStatus.AVAILABLE,
        drift_score=population_stability_index(baseline, current),
        drift_method="psi",
        sample_count=len(current),
        baseline_distribution=_binned_distribution(baseline, edges),
        current_distribution=_binned_distribution(current, edges),
    )
