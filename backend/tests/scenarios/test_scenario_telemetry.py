"""Scenario-execution telemetry integration (Phase 3 Prompt 8 remediation).

Drives the real scenario orchestration/execution pipeline and asserts one scenario
run metric per genuine execution (idempotent reuse is never re-counted), correct
success/failure exclusivity, and fail-open telemetry.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.unit_of_work import UnitOfWork
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.services.scenarios.orchestration import ScenarioOrchestrationService
from tests.scenarios.conftest import AS_OF


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def test_scenario_run_emits_single_sample(seeded_novabank, db_session: Session, novabank_tenant):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][0]

    p = InMemoryObservabilityProvider()
    set_observability_provider(p)
    try:
        bundle = orch.run(novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF)
        uow.commit()
    finally:
        reset_observability_provider()

    assert bundle.reused_existing is False
    assert p.counter_total(MetricName.SCENARIO_RUNS) == 1
    assert p.histogram_values(MetricName.SCENARIO_DURATION)
    # Demo prediction is a deterministic scorecard fallback.
    assert p.counter_total(MetricName.SCENARIO_FALLBACKS) == 1


def test_idempotent_reuse_not_recounted(seeded_novabank, db_session: Session, novabank_tenant):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][0]
    orch.run(novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF)
    uow.commit()

    p = InMemoryObservabilityProvider()
    set_observability_provider(p)
    try:
        uow2 = UnitOfWork(db_session)
        again = ScenarioOrchestrationService(uow2).run(
            novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF
        )
    finally:
        reset_observability_provider()

    assert again.reused_existing is True
    # Reuse is a read of a persisted result — it must not emit a run metric.
    assert p.counter_total(MetricName.SCENARIO_RUNS) == 0


def test_rollback_discards_pending_scenario_success(
    seeded_novabank, db_session: Session, novabank_tenant
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][3]

    p = InMemoryObservabilityProvider()
    set_observability_provider(p)
    try:
        orch.run(novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF)
        # Success is queued until commit — rollback must discard it.
        assert p.counter_total(MetricName.SCENARIO_RUNS) == 0
        uow.rollback()
        assert p.counter_total(MetricName.SCENARIO_RUNS) == 0
    finally:
        reset_observability_provider()


def test_scenario_failure_reported_as_failed(
    seeded_novabank, db_session: Session, novabank_tenant, monkeypatch
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][1]

    def _boom(*args, **kwargs):
        raise RuntimeError("scenario engine failure")

    monkeypatch.setattr(orch._execution._graph, "apply", _boom)

    p = InMemoryObservabilityProvider()
    set_observability_provider(p)
    try:
        with pytest.raises(RuntimeError):
            orch.run(novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF)
    finally:
        reset_observability_provider()

    assert p.counter_total(MetricName.SCENARIO_RUNS, outcome="failed") == 1
    assert p.counter_total(MetricName.SCENARIO_RUNS, outcome="succeeded") == 0


def test_telemetry_failure_does_not_break_scenario(
    seeded_novabank, db_session: Session, novabank_tenant
):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

        def record_value(self, *a, **k):
            raise RuntimeError("boom")

    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][2]
    set_observability_provider(ExplodingProvider())
    try:
        bundle = orch.run(novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF)
        assert bundle.result is not None
    finally:
        reset_observability_provider()
