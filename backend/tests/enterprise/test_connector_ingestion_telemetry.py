"""Runtime connector/ingestion telemetry integration (Phase 3 Prompt 8 remediation).

These call the *real* ``IngestionService`` at its committed boundaries and assert
the emitted metrics on the deterministic ``InMemoryObservabilityProvider``. They
prove connector outcome/latency and ingestion lag/freshness are measured during
real operations (not only from unit tests of the recorders).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.enterprise_enums import (
    DataSourceType,
    EnterpriseEntityType,
    EvidenceSignalType,
    IngestionRunStatus,
)
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.security.context import internal_system_context
from app.security.enums import SecurityRole
from app.services.enterprise.enterprise_services import IngestionService

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _ctx(tenant: str = "novabank"):
    return internal_system_context(
        tenant,
        correlation_id="telemetry-test",
        roles=frozenset({SecurityRole.INTEGRATION_OPERATOR}),
    )


def _register_source(svc: IngestionService, ctx) -> str:
    source = svc.register_data_source(
        ctx, source_type=DataSourceType.GITHUB, display_name="Telemetry GH"
    )
    return source.data_source_id


def _start_run(svc: IngestionService, ctx, ds_id: str) -> str:
    run = svc.start_run(ctx, data_source_id=ds_id)
    return run.ingestion_run_id


def test_successful_sync_emits_single_connector_metric(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    run_id = _start_run(svc, ctx, ds_id)
    obs_provider.reset()  # measure only the completion

    svc.complete_run(
        ctx,
        ingestion_run_id=run_id,
        status=IngestionRunStatus.SUCCEEDED,
        records_read=10,
        records_written=7,
        records_skipped=3,
    )

    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS) == 1
    assert (
        obs_provider.counter_total(
            MetricName.CONNECTOR_SYNCS, outcome="success", connector_type="github"
        )
        == 1
    )
    # success and failure are mutually exclusive for one logical attempt
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="failure") == 0
    assert obs_provider.counter_total(MetricName.CONNECTOR_RECORDS_OBSERVED) == 10
    assert obs_provider.counter_total(MetricName.CONNECTOR_RECORDS_ACCEPTED) == 7
    assert obs_provider.counter_total(MetricName.CONNECTOR_RECORDS_DEDUPLICATED) == 3
    assert obs_provider.histogram_values(MetricName.CONNECTOR_SYNC_DURATION)


def test_failed_sync_emits_failure_outcome(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    run_id = _start_run(svc, ctx, ds_id)
    obs_provider.reset()

    svc.complete_run(ctx, ingestion_run_id=run_id, status=IngestionRunStatus.FAILED, records_read=4)

    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="failure") == 1
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="success") == 0


def test_partial_sync_reported_as_partial_not_success(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    run_id = _start_run(svc, ctx, ds_id)
    obs_provider.reset()

    svc.complete_run(
        ctx,
        ingestion_run_id=run_id,
        status=IngestionRunStatus.PARTIAL,
        records_read=5,
        records_written=3,
    )

    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="partial") == 1
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="success") == 0


def _append(svc, ctx, ds_id, *, event_time, source_record_id="rec-1"):
    return svc.append_evidence(
        ctx,
        data_source_id=ds_id,
        source_record_id=source_record_id,
        signal_type=EvidenceSignalType.COMMIT,
        subject_type=EnterpriseEntityType.REPOSITORY,
        subject_id="repo-1",
        payload={"kind": "commit", "sha": source_record_id},
        event_time=event_time,
        observed_at=AS_OF,
    )


def test_evidence_emits_lag_and_freshness(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    obs_provider.reset()

    # Event a few hours old -> positive lag, fresh/aging freshness age.
    event_time = datetime.now(timezone.utc) - timedelta(hours=2)
    _append(svc, ctx, ds_id, event_time=event_time)

    lags = obs_provider.histogram_values(MetricName.CONNECTOR_INGESTION_LAG, source_type="github")
    ages = obs_provider.histogram_values(MetricName.CONNECTOR_FRESHNESS_AGE, source_type="github")
    assert lags and lags[0] > 0
    assert ages and ages[0] > 0


def test_stale_evidence_freshness_state(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    obs_provider.reset()

    # Well beyond the 24h github stale threshold.
    event_time = datetime.now(timezone.utc) - timedelta(days=3)
    _append(svc, ctx, ds_id, event_time=event_time)

    stale = obs_provider.histogram_values(
        MetricName.CONNECTOR_FRESHNESS_AGE, source_type="github", freshness_state="stale"
    )
    assert stale


def test_clock_skew_event_emits_no_fabricated_lag(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    obs_provider.reset()

    # Future event time -> clock skew: no lag, no freshness age fabricated.
    event_time = datetime.now(timezone.utc) + timedelta(hours=6)
    _append(svc, ctx, ds_id, event_time=event_time)

    assert obs_provider.histogram_values(MetricName.CONNECTOR_INGESTION_LAG) == []
    assert obs_provider.histogram_values(MetricName.CONNECTOR_FRESHNESS_AGE) == []


def test_deduplicated_append_still_returns_created_flag(uow, obs_provider):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    event_time = datetime.now(timezone.utc) - timedelta(hours=1)
    _, created_first = _append(svc, ctx, ds_id, event_time=event_time)
    _, created_second = _append(svc, ctx, ds_id, event_time=event_time)
    assert created_first is True
    assert created_second is False  # deduplicated, not overwritten


def test_telemetry_provider_failure_does_not_break_sync(uow):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

        def record_value(self, *a, **k):
            raise RuntimeError("boom")

    set_observability_provider(ExplodingProvider())
    try:
        svc = IngestionService(uow)
        ctx = _ctx()
        ds_id = _register_source(svc, ctx)
        run_id = _start_run(svc, ctx, ds_id)
        # Business result must be unaffected by telemetry export failures.
        result = svc.complete_run(
            ctx, ingestion_run_id=run_id, status=IngestionRunStatus.SUCCEEDED, records_read=1
        )
        assert result.status == IngestionRunStatus.SUCCEEDED
    finally:
        reset_observability_provider()


def test_idempotent_terminal_completion_does_not_double_count(uow, obs_provider):
    from app.services.enterprise.exceptions import EnterpriseValidationError

    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    run_id = _start_run(svc, ctx, ds_id)
    obs_provider.reset()
    svc.complete_run(ctx, ingestion_run_id=run_id, status=IngestionRunStatus.SUCCEEDED)
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS) == 1
    with pytest.raises(EnterpriseValidationError):
        svc.complete_run(ctx, ingestion_run_id=run_id, status=IngestionRunStatus.SUCCEEDED)
    # Terminal re-completion is rejected before telemetry — still exactly one.
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS) == 1


def test_authorization_denial_is_not_connector_failure(uow, obs_provider):
    from app.security.exceptions import AuthorizationError

    svc = IngestionService(uow)
    operator = _ctx()
    ds_id = _register_source(svc, operator)
    run_id = _start_run(svc, operator, ds_id)
    # Reader context: authenticated but lacking CONNECTORS_SYNC.
    denied = internal_system_context(
        "novabank",
        correlation_id="denied",
        roles=frozenset({SecurityRole.EXECUTIVE_READER}),
    )
    obs_provider.reset()
    with pytest.raises(AuthorizationError):
        svc.complete_run(denied, ingestion_run_id=run_id, status=IngestionRunStatus.SUCCEEDED)
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS) == 0
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="failure") == 0


def test_commit_failure_does_not_emit_connector_success(uow, obs_provider, monkeypatch):
    svc = IngestionService(uow)
    ctx = _ctx()
    ds_id = _register_source(svc, ctx)
    run_id = _start_run(svc, ctx, ds_id)
    obs_provider.reset()

    def _boom_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(svc, "_commit", _boom_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        svc.complete_run(ctx, ingestion_run_id=run_id, status=IngestionRunStatus.SUCCEEDED)
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="success") == 0
    assert obs_provider.counter_total(MetricName.CONNECTOR_SYNCS) == 0
