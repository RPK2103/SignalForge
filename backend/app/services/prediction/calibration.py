"""Platt/sigmoid probability calibration helpers wrapping math_utils."""

from __future__ import annotations

from app.services.prediction import math_utils


def fit_platt_calibrator(
    uncalibrated_probs: list[float],
    labels: list[int],
) -> tuple[float, float]:
    """Fit Platt scaling on calibration-partition probabilities only.

    Returns ``(slope, intercept)`` for ``sigmoid(slope * logit(p) + intercept)``.
    """
    if len(uncalibrated_probs) != len(labels):
        raise ValueError("Platt fit requires aligned probability and label lists")
    if len(labels) < 2:
        raise ValueError("Platt fit requires at least two calibration rows")
    if len(set(labels)) < 2:
        # Degenerate single-class calibration: identity transform.
        return 1.0, 0.0
    return math_utils.fit_platt(uncalibrated_probs, labels)


def apply_platt_calibrator(
    uncalibrated_probs: list[float] | float,
    slope: float,
    intercept: float,
) -> list[float] | float:
    """Apply a fitted Platt calibrator to one probability or a list."""
    if isinstance(uncalibrated_probs, (int, float)):
        calibrated = math_utils.apply_platt([float(uncalibrated_probs)], slope, intercept)
        return calibrated[0]
    return math_utils.apply_platt([float(p) for p in uncalibrated_probs], slope, intercept)


def identity_calibrator() -> tuple[float, float]:
    """No-op calibrator (slope=1, intercept=0) used when calibration is skipped."""
    return 1.0, 0.0
