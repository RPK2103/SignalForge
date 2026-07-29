"""Pure-Python math helpers for logistic delivery models (no numpy/sklearn)."""

from __future__ import annotations

import math
import random
from typing import Sequence


def clip(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def std(values: Sequence[float], *, ddof: int = 0) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    if n - ddof <= 0:
        return 0.0
    mu = mean(values)
    variance = sum((v - mu) ** 2 for v in values) / (n - ddof)
    return math.sqrt(variance)


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def logit(p: float, *, eps: float = 1e-12) -> float:
    p = clip(p, eps, 1.0 - eps)
    return math.log(p / (1.0 - p))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def fit_logistic_l2(
    X: Sequence[Sequence[float]],
    y: Sequence[int | float],
    *,
    seed: int = 42,
    l2: float = 1.0,
    max_iter: int = 500,
    lr: float = 0.1,
) -> tuple[list[float], float]:
    """Fit L2-regularized logistic regression via gradient descent.

    Returns (coefficients, intercept). Weights initialize at zero for
    determinism (seed reserved for future stochastic variants).
    """
    if len(X) == 0:
        raise ValueError("X must be non-empty")
    if len(X) != len(y):
        raise ValueError("X and y length mismatch")
    n_features = len(X[0])
    for row in X:
        if len(row) != n_features:
            raise ValueError("Inconsistent feature dimension")

    _ = seed  # API stability; zero init is deterministic without RNG
    coef = [0.0] * n_features
    intercept = 0.0
    n = float(len(X))
    labels = [float(v) for v in y]

    for _ in range(max_iter):
        grad = [0.0] * n_features
        grad_b = 0.0
        for row, label in zip(X, labels, strict=True):
            z = _dot(coef, row) + intercept
            pred = sigmoid(z)
            err = pred - label
            for j, xj in enumerate(row):
                grad[j] += err * xj
            grad_b += err
        for j in range(n_features):
            grad[j] = grad[j] / n + l2 * coef[j]
            coef[j] -= lr * grad[j]
        intercept -= lr * (grad_b / n)
    return coef, intercept


def predict_proba(
    X: Sequence[Sequence[float]],
    coef: Sequence[float],
    intercept: float,
) -> list[float]:
    return [sigmoid(_dot(coef, row) + intercept) for row in X]


def fit_platt(
    uncalibrated_probs: Sequence[float],
    y: Sequence[int | float],
    *,
    max_iter: int = 200,
    lr: float = 0.1,
) -> tuple[float, float]:
    """Fit Platt scaling: P = sigmoid(a * logit(p) + b)."""
    if len(uncalibrated_probs) != len(y):
        raise ValueError("probabilities and labels length mismatch")
    if not uncalibrated_probs:
        return 1.0, 0.0
    xs = [logit(float(p)) for p in uncalibrated_probs]
    labels = [float(v) for v in y]
    a = 1.0
    b = 0.0
    n = float(len(xs))
    for _ in range(max_iter):
        grad_a = 0.0
        grad_b = 0.0
        for x, label in zip(xs, labels, strict=True):
            pred = sigmoid(a * x + b)
            err = pred - label
            grad_a += err * x
            grad_b += err
        a -= lr * (grad_a / n)
        b -= lr * (grad_b / n)
    return a, b


def apply_platt(probs: Sequence[float], slope: float, intercept: float) -> list[float]:
    return [sigmoid(slope * logit(float(p)) + intercept) for p in probs]


def brier_score(probs: Sequence[float], y: Sequence[int | float]) -> float:
    if len(probs) != len(y):
        raise ValueError("length mismatch")
    if not probs:
        return 0.0
    return mean([(float(p) - float(t)) ** 2 for p, t in zip(probs, y, strict=True)])


def log_loss(probs: Sequence[float], y: Sequence[int | float], *, eps: float = 1e-15) -> float:
    if len(probs) != len(y):
        raise ValueError("length mismatch")
    if not probs:
        return 0.0
    total = 0.0
    for p, t in zip(probs, y, strict=True):
        p = clip(float(p), eps, 1.0 - eps)
        label = float(t)
        total += -(label * math.log(p) + (1.0 - label) * math.log(1.0 - p))
    return total / len(probs)


def roc_auc(probs: Sequence[float], y: Sequence[int | float]) -> float | None:
    """Mann-Whitney AUC; None if only one class is present."""
    if len(probs) != len(y) or not probs:
        return None
    pos = [float(p) for p, t in zip(probs, y, strict=True) if int(t) == 1]
    neg = [float(p) for p, t in zip(probs, y, strict=True) if int(t) == 0]
    if not pos or not neg:
        return None
    pairs = 0.0
    ties = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                pairs += 1.0
            elif p == n:
                ties += 1.0
    return (pairs + 0.5 * ties) / (len(pos) * len(neg))


def average_precision(probs: Sequence[float], y: Sequence[int | float]) -> float | None:
    if len(probs) != len(y) or not probs:
        return None
    positives = sum(1 for t in y if int(t) == 1)
    if positives == 0:
        return None
    order = sorted(range(len(probs)), key=lambda i: float(probs[i]), reverse=True)
    hit = 0
    ap = 0.0
    for rank, idx in enumerate(order, start=1):
        if int(y[idx]) == 1:
            hit += 1
            ap += hit / rank
    return ap / positives


def reliability_bins(
    probs: Sequence[float],
    y: Sequence[int | float],
    *,
    n_bins: int = 10,
) -> list[dict[str, float | int]]:
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    bins: list[dict[str, float | int]] = []
    for b in range(n_bins):
        lo = b / n_bins
        hi = (b + 1) / n_bins
        idxs = [
            i
            for i, p in enumerate(probs)
            if (float(p) >= lo and float(p) < hi) or (b == n_bins - 1 and float(p) == hi)
        ]
        count = len(idxs)
        if count == 0:
            bins.append(
                {
                    "bin": b,
                    "lower": lo,
                    "upper": hi,
                    "count": 0,
                    "avg_predicted": 0.0,
                    "avg_actual": 0.0,
                }
            )
            continue
        avg_pred = mean([float(probs[i]) for i in idxs])
        avg_act = mean([float(y[i]) for i in idxs])
        bins.append(
            {
                "bin": b,
                "lower": lo,
                "upper": hi,
                "count": count,
                "avg_predicted": avg_pred,
                "avg_actual": avg_act,
            }
        )
    return bins


def ece(
    probs: Sequence[float],
    y: Sequence[int | float],
    *,
    n_bins: int = 10,
) -> float:
    if len(probs) != len(y):
        raise ValueError("length mismatch")
    if not probs:
        return 0.0
    bins = reliability_bins(probs, y, n_bins=n_bins)
    total = float(len(probs))
    return sum(
        (float(b["count"]) / total) * abs(float(b["avg_predicted"]) - float(b["avg_actual"]))
        for b in bins
        if int(b["count"]) > 0
    )


def seeded_uniform(seed: int, n: int) -> list[float]:
    """Deterministic [0,1) draws (exposed for tests / weight init experiments)."""
    rng = random.Random(seed)
    return [rng.random() for _ in range(n)]
