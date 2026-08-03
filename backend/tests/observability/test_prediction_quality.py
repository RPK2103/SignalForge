"""Prediction calibration + drift snapshot tests (Phase 3 Prompt 8)."""

from __future__ import annotations

from app.observability.prediction_quality import (
    PredictionQualityStatus,
    brier_score,
    build_calibration_snapshot,
    build_drift_snapshot,
    expected_calibration_error,
    population_stability_index,
)


def test_brier_score_perfect():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0


def test_calibration_error_bounds():
    probs = [i / 100 for i in range(100)]
    outcomes = [1 if p >= 0.5 else 0 for p in probs]
    ece = expected_calibration_error(probs, outcomes)
    assert 0.0 <= ece <= 1.0


def test_no_labels_is_unavailable_not_zero():
    snap = build_calibration_snapshot(probabilities=[0.5, 0.6, 0.7], outcomes=[None, None, None])
    assert snap.status is PredictionQualityStatus.UNAVAILABLE
    assert snap.brier_score is None
    assert snap.calibration_error is None


def test_insufficient_samples():
    snap = build_calibration_snapshot(probabilities=[0.5, 0.6], outcomes=[1, 0])
    assert snap.status is PredictionQualityStatus.INSUFFICIENT_DATA


def test_available_snapshot_deterministic():
    probs = [i / 50 for i in range(50)]
    outcomes = [1 if p >= 0.5 else 0 for p in probs]
    a = build_calibration_snapshot(probabilities=probs, outcomes=outcomes)
    b = build_calibration_snapshot(probabilities=probs, outcomes=outcomes)
    assert a.status is PredictionQualityStatus.AVAILABLE
    assert a.brier_score == b.brier_score
    assert a.label_coverage == 1.0


def test_drift_insufficient_data():
    snap = build_drift_snapshot(baseline=[0.1, 0.2], current=[0.3])
    assert snap.status is PredictionQualityStatus.INSUFFICIENT_DATA


def test_drift_available():
    baseline = [0.1] * 30
    current = [0.9] * 30
    snap = build_drift_snapshot(baseline=baseline, current=current)
    assert snap.status is PredictionQualityStatus.AVAILABLE
    assert snap.drift_method == "psi"
    assert snap.drift_score is not None and snap.drift_score > 0


def test_psi_zero_for_identical():
    dist = [0.05 * i for i in range(20)]
    assert population_stability_index(dist, dist) == 0.0
