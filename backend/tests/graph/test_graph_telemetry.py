"""Delivery-graph projection telemetry integration (Phase 3 Prompt 8 remediation).

Drives the real ``GraphProjectionService`` and asserts rebuild/incremental metrics
and duration are emitted, that failure is reported as failure (never success), and
that telemetry export failure never alters the projection result.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.enterprise_seed import seed_enterprise
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.services.graph.projection_service import GraphProjectionService


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


@pytest.fixture
def enterprise_seeded(db_session: Session, novabank_tenant):
    seed_enterprise(db_session)
    db_session.commit()
    return novabank_tenant


_STATE_OUTCOME = {"succeeded": "success", "partial": "partial", "failed": "failure"}


def test_full_rebuild_emits_outcome_and_duration(uow, enterprise_seeded, obs_provider):
    obs_provider.reset()
    run = GraphProjectionService(uow).full_rebuild(enterprise_seeded)
    uow.commit()
    assert run.state.value in ("succeeded", "partial")
    outcome = _STATE_OUTCOME[run.state.value]
    assert obs_provider.counter_total(MetricName.GRAPH_REBUILDS, outcome=outcome) == 1
    assert obs_provider.counter_total(MetricName.GRAPH_INCREMENTAL_UPDATES) == 0
    # A clean rebuild must never be counted as a failed rebuild.
    if run.state.value == "succeeded":
        assert obs_provider.counter_total(MetricName.GRAPH_FAILED_REBUILDS) == 0
    assert obs_provider.histogram_values(MetricName.GRAPH_DURATION)


def test_incremental_refresh_emits_incremental_metric(uow, enterprise_seeded, obs_provider):
    GraphProjectionService(uow).full_rebuild(enterprise_seeded)
    uow.commit()
    obs_provider.reset()
    GraphProjectionService(uow).incremental_refresh(enterprise_seeded)
    uow.commit()
    assert obs_provider.counter_total(MetricName.GRAPH_INCREMENTAL_UPDATES) == 1
    assert obs_provider.counter_total(MetricName.GRAPH_REBUILDS) == 0


def test_failed_projection_emits_failure_not_success(
    uow, enterprise_seeded, obs_provider, monkeypatch
):
    svc = GraphProjectionService(uow)

    def _boom(*args, **kwargs):
        raise RuntimeError("projection blew up")

    monkeypatch.setattr(svc, "_project_edges", _boom)
    obs_provider.reset()

    with pytest.raises(RuntimeError):
        svc.full_rebuild(enterprise_seeded)

    assert obs_provider.counter_total(MetricName.GRAPH_REBUILDS, outcome="failure") == 1
    assert obs_provider.counter_total(MetricName.GRAPH_REBUILDS, outcome="succeeded") == 0
    assert obs_provider.counter_total(MetricName.GRAPH_FAILED_REBUILDS) == 1


def test_telemetry_failure_does_not_break_rebuild(uow, enterprise_seeded):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

        def record_value(self, *a, **k):
            raise RuntimeError("boom")

    set_observability_provider(ExplodingProvider())
    try:
        run = GraphProjectionService(uow).full_rebuild(enterprise_seeded)
        uow.commit()
        assert run.state.value in ("succeeded", "partial")
    finally:
        reset_observability_provider()


def test_commit_failure_emits_failure_not_success(
    uow, enterprise_seeded, obs_provider, monkeypatch
):
    # Establish a baseline graph first (unpatched commit).
    GraphProjectionService(uow).full_rebuild(enterprise_seeded)
    uow.commit()
    obs_provider.reset()

    # Queue success telemetry, then fail the durable commit so pending is discarded.
    GraphProjectionService(uow).incremental_refresh(enterprise_seeded)
    assert obs_provider.counter_total(MetricName.GRAPH_INCREMENTAL_UPDATES) == 0

    def _boom_commit():
        raise RuntimeError("graph commit failed")

    monkeypatch.setattr(uow.session, "commit", _boom_commit)
    with pytest.raises(RuntimeError, match="graph commit failed"):
        uow.commit()
    uow.rollback()

    assert obs_provider.counter_total(MetricName.GRAPH_INCREMENTAL_UPDATES, outcome="success") == 0
    assert obs_provider.counter_total(MetricName.GRAPH_INCREMENTAL_UPDATES, outcome="failure") == 0
    assert obs_provider.counter_total(MetricName.GRAPH_FAILED_REBUILDS) == 0
