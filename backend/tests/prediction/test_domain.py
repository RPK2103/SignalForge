"""Domain model tests for Delivery Prediction."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS, TARGET_DEFINITION
from app.domain.prediction_enums import (
    ApplicabilityStatus,
    EstimateKind,
    ModelState,
    ModelUsageScope,
    OutcomeCategory,
    PredictionDataScope,
    PredictionTargetType,
    ReliabilityStatus,
    RiskBand,
    VerificationStatus,
)
from app.domain.prediction_models import (
    DeliveryOutcome,
    DeliveryPrediction,
    PredictionModel,
    validate_horizon,
)
from app.services.persistence.snapshot_service import snapshot_hash

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def _outcome(**overrides):
    base = {
        "tenant_id": "novabank",
        "delivery_outcome_id": "dout_test_1",
        "target_type": PredictionTargetType.PROJECT,
        "target_id": "proj_x",
        "horizon_days": DEFAULT_HORIZON_DAYS,
        "prediction_cutoff_at": NOW,
        "target_due_at": NOW + timedelta(days=60),
        "observation_window_end_at": NOW + timedelta(days=90),
        "outcome_category": OutcomeCategory.ON_TIME_SUCCESS,
        "binary_label": 1,
        "verification_status": VerificationStatus.VERIFIED,
        "finalized_at": NOW + timedelta(days=90),
        "data_scope": PredictionDataScope.SYNTHETIC,
    }
    base.update(overrides)
    return DeliveryOutcome(**base)


def _prediction(**overrides):
    base = {
        "tenant_id": "novabank",
        "delivery_prediction_id": "dpred_test_1",
        "prediction_run_id": "prun_test_1",
        "target_type": PredictionTargetType.PROJECT,
        "target_id": "proj_x",
        "as_of_at": NOW,
        "horizon_days": DEFAULT_HORIZON_DAYS,
        "estimate_kind": EstimateKind.UNCALIBRATED_SCORE,
        "probability_of_delivery_success": None,
        "uncalibrated_risk_score": 42.0,
        "risk_band": RiskBand.MODERATE,
        "reliability_status": ReliabilityStatus.MODEL_UNAVAILABLE,
        "applicability_status": ApplicabilityStatus.APPLICABLE,
        "data_scope": PredictionDataScope.SYNTHETIC,
        "prediction_hash": snapshot_hash({"k": 1}),
    }
    base.update(overrides)
    return DeliveryPrediction(**base)


def test_outcome_categories_bounded():
    values = {c.value for c in OutcomeCategory}
    assert values == {
        "on_time_success",
        "delayed_success",
        "failed",
        "cancelled",
        "unknown",
        "censored",
    }
    assert len(OutcomeCategory) == 6


def test_binary_label_bounds():
    assert _outcome(binary_label=0).binary_label == 0
    assert _outcome(binary_label=1).binary_label == 1
    with pytest.raises(ValidationError):
        _outcome(binary_label=2)
    with pytest.raises(ValidationError):
        _outcome(binary_label=-1)


def test_horizon_validation():
    assert validate_horizon(90) == 90
    for bad in (0, 15, 45, 100, 365):
        with pytest.raises(ValueError):
            validate_horizon(bad)
    with pytest.raises(ValidationError):
        _outcome(horizon_days=45)


def test_estimate_kind_calibrated_consistency():
    pred = _prediction(
        estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
        probability_of_delivery_success=0.72,
        uncalibrated_risk_score=None,
        risk_band=RiskBand.LOW,
    )
    assert pred.probability_of_delivery_success == 0.72
    assert pred.uncalibrated_risk_score is None
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=None,
            uncalibrated_risk_score=None,
        )
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=0.5,
            uncalibrated_risk_score=40.0,
        )


def test_estimate_kind_uncalibrated_consistency():
    pred = _prediction(
        estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
        uncalibrated_risk_score=55.0,
        probability_of_delivery_success=None,
    )
    assert pred.uncalibrated_risk_score == 55.0
    assert pred.probability_of_delivery_success is None
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            uncalibrated_risk_score=None,
            probability_of_delivery_success=None,
        )
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            uncalibrated_risk_score=40.0,
            probability_of_delivery_success=0.6,
        )


def test_estimate_kind_insufficient_consistency():
    pred = _prediction(
        estimate_kind=EstimateKind.INSUFFICIENT_DATA,
        probability_of_delivery_success=None,
        uncalibrated_risk_score=None,
        risk_band=RiskBand.HIGH,
    )
    assert pred.probability_of_delivery_success is None
    assert pred.uncalibrated_risk_score is None
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.INSUFFICIENT_DATA,
            probability_of_delivery_success=0.5,
            uncalibrated_risk_score=None,
        )
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.INSUFFICIENT_DATA,
            probability_of_delivery_success=None,
            uncalibrated_risk_score=30.0,
        )


def test_synthetic_model_production_eligible_rejected():
    with pytest.raises(ValidationError):
        PredictionModel(
            tenant_id="novabank",
            prediction_model_id="pmod_x",
            model_name="logistic_delivery_v1",
            model_type="regularized_logistic_regression",
            model_version="v1",
            target_definition=TARGET_DEFINITION,
            horizon_days=90,
            dataset_manifest_id="pdm_x",
            training_code_version="prediction_training_v1",
            parameter_payload={},
            parameter_hash=snapshot_hash({"a": 1}),
            training_seed=42,
            trained_at=NOW,
            model_state=ModelState.CANDIDATE,
            usage_scope=ModelUsageScope.DEMO,
            data_scope=PredictionDataScope.SYNTHETIC,
            production_eligible=True,
        )
    with pytest.raises(ValidationError):
        PredictionModel(
            tenant_id="novabank",
            prediction_model_id="pmod_y",
            model_name="logistic_delivery_v1",
            model_type="regularized_logistic_regression",
            model_version="v1",
            target_definition=TARGET_DEFINITION,
            horizon_days=90,
            dataset_manifest_id="pdm_y",
            training_code_version="prediction_training_v1",
            parameter_payload={},
            parameter_hash=snapshot_hash({"b": 1}),
            training_seed=42,
            trained_at=NOW,
            model_state=ModelState.CANDIDATE,
            usage_scope=ModelUsageScope.PRODUCTION,
            data_scope=PredictionDataScope.SYNTHETIC,
            production_eligible=False,
        )


def test_risk_score_bounds():
    assert _prediction(uncalibrated_risk_score=0.0).uncalibrated_risk_score == 0.0
    assert _prediction(uncalibrated_risk_score=100.0).uncalibrated_risk_score == 100.0
    with pytest.raises(ValidationError):
        _prediction(uncalibrated_risk_score=-0.1)
    with pytest.raises(ValidationError):
        _prediction(uncalibrated_risk_score=100.1)


def test_probability_bounds():
    assert (
        _prediction(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=0.0,
            uncalibrated_risk_score=None,
            risk_band=RiskBand.CRITICAL,
        ).probability_of_delivery_success
        == 0.0
    )
    assert (
        _prediction(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=1.0,
            uncalibrated_risk_score=None,
            risk_band=RiskBand.LOW,
        ).probability_of_delivery_success
        == 1.0
    )
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=-0.01,
            uncalibrated_risk_score=None,
        )
    with pytest.raises(ValidationError):
        _prediction(
            estimate_kind=EstimateKind.CALIBRATED_PROBABILITY,
            probability_of_delivery_success=1.01,
            uncalibrated_risk_score=None,
        )


def test_censored_unlabeled():
    censored = _outcome(
        outcome_category=OutcomeCategory.CENSORED,
        binary_label=None,
        verification_status=VerificationStatus.EXCLUDED,
        finalized_at=None,
        actual_completed_at=None,
    )
    assert censored.binary_label is None
    with pytest.raises(ValidationError):
        _outcome(
            outcome_category=OutcomeCategory.CENSORED,
            binary_label=1,
            verification_status=VerificationStatus.EXCLUDED,
            finalized_at=None,
        )
    with pytest.raises(ValidationError):
        _outcome(
            outcome_category=OutcomeCategory.UNKNOWN,
            binary_label=0,
            verification_status=VerificationStatus.PENDING,
            finalized_at=None,
        )
