"""Delivery Prediction Engine services (Phase 3 Prompt 4)."""

from app.services.prediction.applicability import check_applicability
from app.services.prediction.backtesting import PredictionBacktestService
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.calibration import (
    apply_platt_calibrator,
    fit_platt_calibrator,
)
from app.services.prediction.dataset_builder import PredictionDatasetBuilder
from app.services.prediction.evaluation import PredictionEvaluationService
from app.services.prediction.explanations import (
    build_explanation_summary,
    build_logistic_factors,
    build_scorecard_factors,
)
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.prediction.feature_schema import (
    FEATURE_DEFINITIONS,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    FeatureDefinition,
    feature_schema_hash,
    get_feature_meta,
    validate_feature_values,
)
from app.services.prediction.inference import PredictionInferenceService
from app.services.prediction.leakage import PredictionLeakageValidator
from app.services.prediction.math_utils import (
    apply_platt,
    average_precision,
    brier_score,
    clip,
    ece,
    fit_logistic_l2,
    fit_platt,
    log_loss,
    logit,
    mean,
    predict_proba,
    reliability_bins,
    roc_auc,
    sigmoid,
    std,
)
from app.services.prediction.orchestration import (
    PredictionOrchestrationService,
    PredictionOrchestrator,
)
from app.services.prediction.registry import PredictionModelRegistry
from app.services.prediction.training import PredictionTrainingService

__all__ = [
    "FEATURE_DEFINITIONS",
    "FEATURE_NAMES",
    "FEATURE_SCHEMA_VERSION",
    "DeliveryScorecardV1",
    "FeatureDefinition",
    "FeatureExtractor",
    "PredictionBacktestService",
    "PredictionDatasetBuilder",
    "PredictionEvaluationService",
    "PredictionInferenceService",
    "PredictionLeakageValidator",
    "PredictionModelRegistry",
    "PredictionOrchestrationService",
    "PredictionOrchestrator",
    "PredictionTrainingService",
    "apply_platt",
    "apply_platt_calibrator",
    "average_precision",
    "brier_score",
    "build_explanation_summary",
    "build_logistic_factors",
    "build_scorecard_factors",
    "check_applicability",
    "clip",
    "ece",
    "feature_schema_hash",
    "fit_logistic_l2",
    "fit_platt",
    "fit_platt_calibrator",
    "get_feature_meta",
    "log_loss",
    "logit",
    "mean",
    "predict_proba",
    "reliability_bins",
    "roc_auc",
    "sigmoid",
    "std",
    "validate_feature_values",
]
