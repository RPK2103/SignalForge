"""Delivery Prediction enums (Phase 3 Prompt 4).

Bounded identifiers for outcomes, models, and inference. Calibrated
probabilities are produced only by validated statistical models — never by
readiness scores, assessment confidence, graph confidence, or LLM calls.
"""

from enum import Enum


class PredictionTargetType(str, Enum):
    PROJECT = "project"
    INITIATIVE = "initiative"


class OutcomeCategory(str, Enum):
    ON_TIME_SUCCESS = "on_time_success"
    DELAYED_SUCCESS = "delayed_success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    CENSORED = "censored"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    EXCLUDED = "excluded"


class PredictionDataScope(str, Enum):
    SYNTHETIC = "synthetic"
    PUBLIC = "public"
    CUSTOMER_CONSENTED = "customer_consented"


class EstimateKind(str, Enum):
    CALIBRATED_PROBABILITY = "calibrated_probability"
    UNCALIBRATED_SCORE = "uncalibrated_score"
    INSUFFICIENT_DATA = "insufficient_data"


class RiskBand(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ModelState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    ACTIVE = "active"
    REJECTED = "rejected"
    RETIRED = "retired"


class ModelUsageScope(str, Enum):
    DEMO = "demo"
    EVALUATION = "evaluation"
    PRODUCTION = "production"


class PredictionRunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReliabilityStatus(str, Enum):
    VALIDATED = "validated"
    LIMITED = "limited"
    INSUFFICIENT_HISTORY = "insufficient_history"
    STALE_DATA = "stale_data"
    OUT_OF_DISTRIBUTION = "out_of_distribution"
    MODEL_UNAVAILABLE = "model_unavailable"


class ApplicabilityStatus(str, Enum):
    APPLICABLE = "applicable"
    DEGRADED = "degraded"
    NOT_APPLICABLE = "not_applicable"


class EvaluationSplit(str, Enum):
    TRAIN = "train"
    CALIBRATION = "calibration"
    TEST = "test"
    BACKTEST_FOLD = "backtest_fold"


class FactorSourceKind(str, Enum):
    LOGISTIC_CONTRIBUTION = "logistic_contribution"
    SCORECARD_RULE = "scorecard_rule"


class PredictionDataQualityWarning(str, Enum):
    FEATURE_OUTSIDE_TRAINING_RANGE = "feature_outside_training_range"
    HIGH_MISSINGNESS = "high_missingness"
    STALE_EVIDENCE = "stale_evidence"
    INSUFFICIENT_HISTORY = "insufficient_history"
    GRAPH_NOT_CURRENT = "graph_not_current"
    MODEL_NOT_VALIDATED = "model_not_validated"
    SYNTHETIC_MODEL = "synthetic_model"
    UNRESOLVED_TARGET = "unresolved_target"
    UNSUPPORTED_HORIZON = "unsupported_horizon"
    MISSING_OWNER = "missing_owner"
    STALE_SOURCE = "stale_source"
    INCOMPLETE_HISTORY = "incomplete_history"
    GRAPH_UNAVAILABLE = "graph_unavailable"
    BASELINE_FALLBACK = "baseline_fallback"
    ONE_CLASS_DATASET = "one_class_dataset"
    LEAKAGE_BLOCKED = "leakage_blocked"
