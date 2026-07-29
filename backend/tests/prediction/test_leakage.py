"""Leakage validation tests for delivery prediction."""

from datetime import datetime, timedelta, timezone

from app.services.prediction.feature_schema import FEATURE_NAMES
from app.services.prediction.leakage import PredictionLeakageValidator

CUTOFF = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _clean_row(**overrides):
    values = {name: 0.0 for name in FEATURE_NAMES}
    row = {
        "prediction_cutoff_at": CUTOFF,
        "as_of_at": CUTOFF,
        "evidence_cutoff_at": CUTOFF,
        "feature_values": values,
        "feature_lineage": [
            {
                "feature_name": "readiness_score_at_cutoff",
                "source_entity_type": "assessment",
                "source_entity_id": "a1",
                "source_timestamp": (CUTOFF - timedelta(days=1)).isoformat(),
                "transformation_rule": "identity",
                "transformation_version": "v1",
            }
        ],
        "source_timestamps": {"evidence": (CUTOFF - timedelta(hours=2)).isoformat()},
        "uses_current_graph_state": False,
        "uses_test_statistics_for_scaling": False,
        "uses_test_statistics_for_imputation": False,
        "calibrator_fit_on_test": False,
    }
    row.update(overrides)
    return row


def test_future_evidence_rejected():
    validator = PredictionLeakageValidator()
    row = _clean_row(
        evidence_cutoff_at=CUTOFF + timedelta(days=1),
        source_timestamps={"evidence": (CUTOFF + timedelta(hours=3)).isoformat()},
    )
    reasons = validator.validate_row(row)
    assert "evidence_cutoff_after_prediction_cutoff" in reasons
    assert any(r.startswith("source_timestamp_after_cutoff:") for r in reasons)


def test_outcome_label_in_features_rejected():
    validator = PredictionLeakageValidator()
    values = {name: 0.0 for name in FEATURE_NAMES}
    values["binary_label"] = 1.0
    values["outcome_category"] = 1.0
    reasons = validator.validate_row(_clean_row(feature_values=values))
    assert any("outcome_label_in_features:binary_label" in r for r in reasons)
    assert any("outcome_label_in_features:outcome_category" in r for r in reasons)


def test_actual_completed_at_as_feature_rejected():
    validator = PredictionLeakageValidator()
    values = {name: 0.0 for name in FEATURE_NAMES}
    values["actual_completed_at"] = 1.0
    reasons = validator.validate_row(
        _clean_row(
            feature_values=values,
            actual_completed_at=CUTOFF + timedelta(days=40),
        )
    )
    assert any("actual_completed" in r for r in reasons)


def test_clean_report_when_valid():
    validator = PredictionLeakageValidator()
    rows = [_clean_row(), _clean_row()]
    report = validator.validate_dataset(rows)
    assert report.clean is True
    assert report.rows_rejected == 0
    assert report.cutoff_violations == 0
    assert len(report.report_hash) == 64


def test_adversarial_leakage_patterns():
    validator = PredictionLeakageValidator()
    values = {name: 0.0 for name in FEATURE_NAMES}
    values["salary_band"] = 3.0
    forbidden = validator.validate_row(_clean_row(feature_values=values))
    assert any(r.startswith("forbidden_feature:") for r in forbidden)

    graph_state = validator.validate_row(_clean_row(uses_current_graph_state=True))
    assert "current_graph_state_substituted" in graph_state

    test_stats = validator.validate_row(
        _clean_row(
            uses_test_statistics_for_scaling=True,
            calibrator_fit_on_test=True,
        )
    )
    assert "test_statistics_used_for_scaling" in test_stats
    assert "calibration_used_test_labels" in test_stats

    lineage_future = validator.validate_row(
        _clean_row(
            feature_lineage=[
                {
                    "feature_name": "active_dependency_count",
                    "source_entity_type": "graph_edge",
                    "source_entity_id": "e1",
                    "source_timestamp": (CUTOFF + timedelta(days=2)).isoformat(),
                    "transformation_rule": "count",
                    "transformation_version": "v1",
                }
            ]
        )
    )
    assert "lineage_source_after_cutoff" in lineage_future
