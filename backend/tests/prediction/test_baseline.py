"""Baseline scorecard tests for delivery prediction."""

from app.domain.prediction_enums import EstimateKind, RiskBand
from app.domain.prediction_models import ScorecardResult
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.feature_schema import FEATURE_NAMES


def _features(**overrides):
    values = {name: 0.0 for name in FEATURE_NAMES}
    values.update(
        {
            "readiness_score_at_cutoff": 70.0,
            "assessment_confidence_at_cutoff": 65.0,
            "capability_coverage": 0.8,
            "critical_capability_gap_count": 0.0,
            "unresolved_critical_risk_count": 0.0,
            "active_dependency_cycle_indicator": 0.0,
            "single_person_dependency_count": 0.0,
            "cross_team_dependency_count": 2.0,
            "finding_severity_critical_count": 0.0,
            "ownership_redundancy": 1.5,
            "unavailable_owner_ratio": 0.1,
            "team_availability_ratio": 0.85,
            "overdue_work_item_count": 1.0,
            "blocked_work_item_count": 0.0,
            "sprint_completion_ratio": 0.7,
            "failed_deployment_count_30d": 0.0,
            "deployment_count_30d": 2.0,
            "unresolved_incident_count": 0.0,
            "missing_owner_indicator": 0.0,
            "incomplete_history_indicator": 0.0,
            "stale_source_count": 0.0,
            "source_coverage_ratio": 0.9,
        }
    )
    values.update(overrides)
    return values


def test_score_determinism():
    scorecard = DeliveryScorecardV1()
    features = _features()
    a = scorecard.score(features, {})
    b = scorecard.score(features, {})
    assert a.delivery_risk_score == b.delivery_risk_score
    assert a.risk_band == b.risk_band
    assert a.model_dump() == b.model_dump()


def test_score_bounds_0_100():
    scorecard = DeliveryScorecardV1()
    low_risk = scorecard.score(
        _features(
            readiness_score_at_cutoff=90.0,
            capability_coverage=0.95,
            ownership_redundancy=3.0,
            team_availability_ratio=0.95,
            sprint_completion_ratio=0.9,
            deployment_count_30d=5.0,
            source_coverage_ratio=0.95,
        ),
        {},
    )
    high_risk = scorecard.score(
        _features(
            readiness_score_at_cutoff=20.0,
            capability_coverage=0.2,
            critical_capability_gap_count=5.0,
            unresolved_critical_risk_count=4.0,
            active_dependency_cycle_indicator=1.0,
            single_person_dependency_count=4.0,
            finding_severity_critical_count=3.0,
            unavailable_owner_ratio=0.8,
            overdue_work_item_count=20.0,
            blocked_work_item_count=10.0,
            sprint_completion_ratio=0.2,
            failed_deployment_count_30d=5.0,
            unresolved_incident_count=4.0,
            missing_owner_indicator=1.0,
            incomplete_history_indicator=1.0,
            stale_source_count=5.0,
        ),
        {},
    )
    assert 0.0 <= low_risk.delivery_risk_score <= 100.0
    assert 0.0 <= high_risk.delivery_risk_score <= 100.0
    assert high_risk.delivery_risk_score >= low_risk.delivery_risk_score


def test_risk_bands():
    scorecard = DeliveryScorecardV1()
    result = scorecard.score(_features(), {})
    assert result.risk_band in {
        RiskBand.LOW,
        RiskBand.MODERATE,
        RiskBand.HIGH,
        RiskBand.CRITICAL,
    }


def test_estimate_kind_uncalibrated_score():
    result = DeliveryScorecardV1().score(_features(), {})
    assert result.estimate_kind == EstimateKind.UNCALIBRATED_SCORE
    assert isinstance(result, ScorecardResult)


def test_no_probability_field_on_scorecard_result():
    result = DeliveryScorecardV1().score(_features(), {})
    fields = set(ScorecardResult.model_fields)
    assert "probability_of_delivery_success" not in fields
    assert "probability" not in fields
    dumped = result.model_dump()
    assert "probability_of_delivery_success" not in dumped
    assert "probability" not in dumped
    assert "delivery_risk_score" in dumped
