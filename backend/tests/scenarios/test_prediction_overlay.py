"""Prediction adapter and feature overlay safety tests."""

from __future__ import annotations

from types import SimpleNamespace

from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_enums import EstimateKind
from app.domain.scenario_enums import ScenarioTargetType
from app.services.prediction.feature_schema import FEATURE_NAMES
from app.services.scenarios.baseline import ScenarioBaseline
from app.services.scenarios.feature_overlay import ScenarioFeatureOverlayService
from app.services.scenarios.graph_overlay import GraphOverlayResult
from app.services.scenarios.prediction_adapter import ScenarioPredictionAdapter
from tests.scenarios.conftest import AS_OF


def test_calibrated_fixture_path_produces_probability_delta(novabank_tenant):
    """Controlled active-model fixture — does not promote NovaBank rejected candidate."""
    feature_list = list(FEATURE_NAMES) + [f"{n}__missing" for n in FEATURE_NAMES]
    n = len(feature_list)
    payload = {
        "feature_list": feature_list,
        "impute_values": [0.0] * n,
        "scale_means": [0.0] * n,
        "scale_stds": [1.0] * n,
        "coefficients": [0.0] * n,
        "intercept": 0.0,
        "calibration_slope": 1.0,
        "calibration_intercept": 0.0,
    }
    idx = feature_list.index("unavailable_owner_ratio")
    payload["coefficients"][idx] = -2.0

    model = SimpleNamespace(
        tenant_id=novabank_tenant.tenant_id,
        prediction_model_id="pmodel_fixture_active",
        model_version="fixture-1",
        horizon_days=90,
        model_state=SimpleNamespace(value="active"),
        parameter_payload=payload,
    )

    class _FakeModels:
        def get_active(self, *args, **kwargs):
            return model

        def get(self, *args, **kwargs):
            return model

    class _FakeUow:
        prediction_models = _FakeModels()

    adapter = ScenarioPredictionAdapter(_FakeUow())  # type: ignore[arg-type]
    baseline = ScenarioBaseline(
        target_type=ScenarioTargetType.PROJECT,
        target_id="proj_x",
        as_of_at=AS_OF,
        horizon_days=90,
        source_fingerprint="a" * 64,
        source_components={},
        baseline_fingerprint="b" * 64,
        graph_projection_version="1",
        graph_node_count=1,
        graph_edge_count=1,
        finding_hashes=[],
        finding_summaries=[],
        feature_snapshot_id=None,
        feature_values={name: 0.0 for name in FEATURE_NAMES},
        missingness={},
        feature_values_hash="c" * 64,
        prediction_model_id=model.prediction_model_id,
        prediction_baseline_version="fixture-1",
        estimate_kind_hint=EstimateKind.CALIBRATED_PROBABILITY,
    )
    simulated = dict(baseline.feature_values)
    simulated["unavailable_owner_ratio"] = 1.0
    pair = adapter.evaluate_pair(
        novabank_tenant,
        baseline=baseline,
        simulated_feature_values=simulated,
        force_model_id=model.prediction_model_id,
    )
    assert pair.baseline.estimate_kind == EstimateKind.CALIBRATED_PROBABILITY
    assert pair.simulated.estimate_kind == EstimateKind.CALIBRATED_PROBABILITY
    assert pair.baseline.probability is not None
    assert pair.simulated.probability is not None
    assert pair.probability_delta is not None
    assert pair.risk_score_delta is None
    assert pair.estimate_comparability.value == "comparable_probability"


def test_failed_candidate_ignored_uses_scorecard(seeded_novabank, db_session, novabank_tenant):
    uow = UnitOfWork(db_session)
    # No active model exists for NovaBank — adapter must use scorecard fallback.
    adapter = ScenarioPredictionAdapter(uow)
    baseline = ScenarioBaseline(
        target_type=ScenarioTargetType.PROJECT,
        target_id="proj_x",
        as_of_at=AS_OF,
        horizon_days=90,
        source_fingerprint="a" * 64,
        source_components={},
        baseline_fingerprint="b" * 64,
        graph_projection_version="1",
        graph_node_count=1,
        graph_edge_count=1,
        finding_hashes=[],
        finding_summaries=[],
        feature_snapshot_id=None,
        feature_values={"unavailable_owner_ratio": 0.1, "active_engineer_owner_count": 3.0},
        missingness={},
        feature_values_hash="c" * 64,
        prediction_model_id=None,
        prediction_baseline_version="delivery_scorecard_v1",
        estimate_kind_hint=EstimateKind.UNCALIBRATED_SCORE,
    )
    pair = adapter.evaluate_pair(
        novabank_tenant,
        baseline=baseline,
        simulated_feature_values={
            "unavailable_owner_ratio": 0.4,
            "active_engineer_owner_count": 2.0,
        },
    )
    assert pair.baseline.estimate_kind == EstimateKind.UNCALIBRATED_SCORE
    assert pair.baseline.probability is None
    assert pair.probability_delta is None
    assert pair.risk_score_delta is not None


def test_feature_overlay_training_ineligible(novabank_tenant):
    service = ScenarioFeatureOverlayService()
    baseline = ScenarioBaseline(
        target_type=ScenarioTargetType.PROJECT,
        target_id="proj_x",
        as_of_at=AS_OF,
        horizon_days=90,
        source_fingerprint="a" * 64,
        source_components={},
        baseline_fingerprint="b" * 64,
        graph_projection_version="1",
        graph_node_count=1,
        graph_edge_count=1,
        finding_hashes=[],
        finding_summaries=[],
        feature_snapshot_id="snap_x",
        feature_values={
            "unavailable_owner_ratio": 0.1,
            "active_engineer_owner_count": 3.0,
            "single_person_dependency_count": 0.0,
            "availability_blast_radius_count": 0.0,
            "ownership_redundancy": 2.0,
            "missing_owner_indicator": 0.0,
        },
        missingness={},
        feature_values_hash="c" * 64,
        prediction_model_id=None,
        prediction_baseline_version="delivery_scorecard_v1",
        estimate_kind_hint=EstimateKind.UNCALIBRATED_SCORE,
    )
    overlay = service.build(
        novabank_tenant,
        scenario_run_id="srun_test",
        assumptions={
            "kind": "engineer_unavailable",
            "changes": [
                {
                    "kind": "engineer_unavailable",
                    "engineer_id": "eng_x",
                    "unavailable_from": AS_OF.isoformat(),
                    "unavailable_until": AS_OF.isoformat(),
                }
            ],
        },
        baseline=baseline,
        graph_overlay=GraphOverlayResult(),
    )
    assert overlay.training_eligible is False
    assert "unavailable_owner_ratio" in overlay.changed_feature_values
    assert overlay.simulated_feature_values["active_engineer_owner_count"] == 2.0
