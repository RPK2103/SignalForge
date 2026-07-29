"""Feature schema contract tests for delivery prediction."""

from app.domain.prediction_constants import FORBIDDEN_FEATURE_TOKENS
from app.services.prediction.feature_schema import (
    FEATURE_DEFINITIONS,
    FEATURE_NAMES,
    feature_schema_hash,
    validate_feature_values,
)


def test_feature_count_at_least_40():
    assert len(FEATURE_NAMES) >= 40
    assert len(FEATURE_DEFINITIONS) == len(FEATURE_NAMES)
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))


def test_schema_hash_stable():
    a = feature_schema_hash()
    b = feature_schema_hash()
    assert a == b
    assert len(a) == 64


def test_forbidden_tokens_rejected_by_validator():
    values = {name: 0.0 for name in FEATURE_NAMES}
    values["manager_sentiment_score"] = 1.0
    warnings = validate_feature_values(values)
    assert any(w.startswith("forbidden_feature_token:") for w in warnings)
    for token in ("email", "salary", "ssn", "performance_rating"):
        assert token in FORBIDDEN_FEATURE_TOKENS


def test_validate_ranges():
    values = {name: 0.0 for name in FEATURE_NAMES}
    values["readiness_score_at_cutoff"] = 150.0
    values["capability_coverage"] = -0.5
    warnings = validate_feature_values(values)
    assert "above_range:readiness_score_at_cutoff" in warnings
    assert "below_range:capability_coverage" in warnings

    clean = {name: 0.0 for name in FEATURE_NAMES}
    clean["readiness_score_at_cutoff"] = 55.0
    clean["capability_coverage"] = 0.8
    clean_warnings = validate_feature_values(clean)
    assert not any(w.startswith("above_range:") for w in clean_warnings)
    assert not any(w.startswith("below_range:") for w in clean_warnings)
