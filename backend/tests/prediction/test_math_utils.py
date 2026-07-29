"""Math utility tests for delivery prediction."""

import math

from app.services.prediction.math_utils import (
    apply_platt,
    brier_score,
    fit_logistic_l2,
    fit_platt,
    log_loss,
    predict_proba,
    seeded_uniform,
)


def test_logistic_reproducibility_fixed_seed():
    X = [
        [0.0, 1.0],
        [1.0, 0.0],
        [0.5, 0.5],
        [1.0, 1.0],
        [0.2, 0.8],
        [0.8, 0.2],
    ]
    y = [0, 1, 1, 0, 0, 1]
    a_coef, a_intercept = fit_logistic_l2(X, y, seed=42, max_iter=100)
    b_coef, b_intercept = fit_logistic_l2(X, y, seed=42, max_iter=100)
    assert a_coef == b_coef
    assert a_intercept == b_intercept
    probs_a = predict_proba(X, a_coef, a_intercept)
    probs_b = predict_proba(X, b_coef, b_intercept)
    assert probs_a == probs_b
    draws = seeded_uniform(42, 5)
    assert draws == seeded_uniform(42, 5)


def test_platt_keeps_probs_in_0_1():
    raw = [0.01, 0.2, 0.5, 0.8, 0.99]
    labels = [0, 0, 1, 1, 1]
    slope, intercept = fit_platt(raw, labels)
    calibrated = apply_platt(raw, slope, intercept)
    assert len(calibrated) == len(raw)
    for p in calibrated:
        assert 0.0 <= p <= 1.0
        assert math.isfinite(p)


def test_brier_logloss_finite():
    probs = [0.1, 0.4, 0.6, 0.9]
    y = [0, 0, 1, 1]
    brier = brier_score(probs, y)
    ll = log_loss(probs, y)
    assert math.isfinite(brier)
    assert math.isfinite(ll)
    assert 0.0 <= brier <= 1.0
    assert ll >= 0.0
