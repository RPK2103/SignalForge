"""Delivery-prediction telemetry integration (Phase 3 Prompt 8 remediation).

Drives the real ``PredictionOrchestrator.predict`` and asserts a single prediction
telemetry sample per inference with the correct outcome mapping: an uncalibrated
scorecard result is a deterministic fallback (never a probability), insufficient
evidence is a missing-data outcome (not a provider failure), and a raised error is
reported as an error outcome without a success sample.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db.enterprise_seed import seed_enterprise
from app.domain.prediction_enums import PredictionTargetType
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.projection_service import GraphProjectionService
from app.services.prediction.orchestration import PredictionOrchestrator

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


@pytest.fixture
def prepared(db_session: Session, novabank_tenant):
    seed_enterprise(db_session)
    db_session.commit()
    from app.db.unit_of_work import UnitOfWork

    uow = UnitOfWork(db_session)
    GraphProjectionService(uow).full_rebuild(novabank_tenant)
    GraphAnalysisService(uow).analyze(novabank_tenant)
    uow.commit()
    project = uow.initiatives_projects.list_projects(novabank_tenant, limit=1, offset=0).items[0]
    return uow, novabank_tenant, project.enterprise_project_id


def test_prediction_emits_single_sample_with_fallback(prepared, obs_provider):
    uow, ctx, project_id = prepared
    obs_provider.reset()
    orch = PredictionOrchestrator(uow)
    bundle = orch.predict(ctx, PredictionTargetType.PROJECT, project_id, AS_OF)
    uow.commit()

    assert obs_provider.counter_total(MetricName.PREDICTIONS) == 1
    assert obs_provider.histogram_values(MetricName.PREDICTION_DURATION)
    # No active calibrated model in the demo seed -> deterministic scorecard fallback.
    assert bundle.prediction.estimate_kind.value == "uncalibrated_score"
    assert obs_provider.counter_total(MetricName.PREDICTION_FALLBACKS) == 1
    # An uncalibrated score is never labelled a probability.
    assert bundle.prediction.probability_of_delivery_success is None
    assert obs_provider.counter_total(MetricName.PREDICTION_MISSING_DATA) == 0


def test_unsupported_horizon_is_missing_data_not_failure(prepared, obs_provider):
    uow, ctx, project_id = prepared
    obs_provider.reset()
    orch = PredictionOrchestrator(uow)
    bundle = orch.predict(ctx, PredictionTargetType.PROJECT, project_id, AS_OF, horizon_days=999)
    uow.commit()

    assert bundle.prediction.estimate_kind.value == "insufficient_data"
    assert obs_provider.counter_total(MetricName.PREDICTIONS) == 1
    assert obs_provider.counter_total(MetricName.PREDICTION_MISSING_DATA) == 1


def test_inference_exception_reported_as_error(prepared, obs_provider, monkeypatch):
    uow, ctx, project_id = prepared
    orch = PredictionOrchestrator(uow)

    def _boom(*args, **kwargs):
        raise RuntimeError("inference blew up")

    monkeypatch.setattr(orch._inference, "predict", _boom)
    obs_provider.reset()

    with pytest.raises(RuntimeError):
        orch.predict(ctx, PredictionTargetType.PROJECT, project_id, AS_OF)

    assert obs_provider.counter_total(MetricName.PREDICTIONS, outcome="error") == 1
    assert obs_provider.counter_total(MetricName.PREDICTION_FALLBACKS) == 0


def test_telemetry_failure_does_not_break_prediction(prepared):
    uow, ctx, project_id = prepared

    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

        def record_value(self, *a, **k):
            raise RuntimeError("boom")

    set_observability_provider(ExplodingProvider())
    try:
        orch = PredictionOrchestrator(uow)
        bundle = orch.predict(ctx, PredictionTargetType.PROJECT, project_id, AS_OF)
        assert bundle.prediction is not None
    finally:
        reset_observability_provider()
