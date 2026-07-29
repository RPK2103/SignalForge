"""Versioned constants for the Delivery Prediction Engine (Prompt 4)."""

from __future__ import annotations

# Explicit prediction target — project/initiative delivery only.
TARGET_DEFINITION = "DELIVERY_SUCCESS_WITHIN_HORIZON"
LABEL_VERSION = "delivery_success_label_v1"
FEATURE_SCHEMA_VERSION = "delivery_features_v1"
SCORECARD_VERSION = "delivery_scorecard_v1"
MODEL_NAME = "logistic_delivery_v1"
MODEL_TYPE = "regularized_logistic_regression"
THRESHOLD_VERSION = "demo_gates_v1"
TRAINING_CODE_VERSION = "prediction_training_v1"
SPLIT_STRATEGY = "temporal_60_20_20_grouped"

SUPPORTED_HORIZONS: frozenset[int] = frozenset({30, 60, 90, 180})
DEFAULT_HORIZON_DAYS = 90

# Minimum labeled-data thresholds (versioned).
MIN_LABELED_ROWS = 60
MIN_POSITIVE_ROWS = 15
MIN_NEGATIVE_ROWS = 15
MIN_CALIBRATION_ROWS = 10
MIN_TEST_ROWS = 10

TRAIN_FRACTION = 0.60
CALIBRATION_FRACTION = 0.20
# Remaining ~20% is final test.

TRAINING_SEED = 42
L2_REGULARIZATION = 1.0
MAX_TRAINING_ITERATIONS = 500
LEARNING_RATE = 0.1

MAX_FEATURE_SNAPSHOT_BYTES = 48_000
MAX_FACTORS = 8
MAX_LINEAGE_ENTRIES = 64
MAX_NOTES_SUMMARY = 512
MAX_DATA_QUALITY_WARNINGS = 32
MAX_EVIDENCE_REFS = 16
MAX_BACKTEST_FOLDS = 8

# Scorecard risk bands (uncalibrated 0–100 risk score).
BAND_LOW_MAX = 25.0
BAND_MODERATE_MAX = 50.0
BAND_HIGH_MAX = 75.0

# Demo validation gates (conservative; not production thresholds).
GATE_MAX_BRIER = 0.35
GATE_MAX_ECE = 0.25
GATE_MAX_BASELINE_BRIER_DELTA = 0.05  # model may underperform baseline by this much

FORBIDDEN_FEATURE_TOKENS: frozenset[str] = frozenset(
    {
        "email",
        "salary",
        "gender",
        "ethnicity",
        "religion",
        "health",
        "political",
        "password",
        "secret",
        "token",
        "ssn",
        "employee_rank",
        "performance_rating",
        "manager_sentiment",
    }
)
