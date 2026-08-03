"""End-to-end domain-metric flow and SLO behavior (Phase 3 Prompt 8 remediation).

Proves the full runtime path for a real service operation:

    service operation -> recorder -> provider -> metric reader -> SLO evaluation

and that domain SLOs consume actual emitted samples (never fabricated), while zero
samples remain ``insufficient_data``.
"""

from __future__ import annotations

import pytest

from app.domain.enterprise_enums import DataSourceType, IngestionRunStatus
from app.observability.attributes import ALLOWED_ATTRIBUTES, DENIED_ATTRIBUTES
from app.observability.metrics_reader import MetricsReader
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import (
    get_observability_provider,
    reset_observability_provider,
    set_observability_provider,
)
from app.security.context import internal_system_context
from app.security.enums import Permission, SecurityRole
from app.services.enterprise.enterprise_services import IngestionService
from app.services.observability.observability_service import ObservabilityService


@pytest.fixture
def installed_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _operator_ctx():
    return internal_system_context(
        "novabank",
        correlation_id="flow",
        roles=frozenset({SecurityRole.INTEGRATION_OPERATOR}),
    )


def _obs_ctx():
    return internal_system_context(
        "novabank",
        correlation_id="flow",
        permissions=frozenset({Permission.OBSERVABILITY_READ, Permission.OBSERVABILITY_MANAGE}),
    )


def _run_successful_syncs(uow, count: int = 5) -> None:
    """Perform ``count`` real connector syncs (the connector SLO needs >= 5 samples)."""
    svc = IngestionService(uow)
    ctx = _operator_ctx()
    ds = svc.register_data_source(ctx, source_type=DataSourceType.GITHUB, display_name="Flow GH")
    for i in range(count):
        run = svc.start_run(ctx, data_source_id=ds.data_source_id, run_key=f"run-{i}")
        svc.complete_run(
            ctx,
            ingestion_run_id=run.ingestion_run_id,
            status=IngestionRunStatus.SUCCEEDED,
            records_read=5,
            records_written=5,
        )


def test_connector_metric_reaches_reader(uow, installed_provider):
    _run_successful_syncs(uow)
    reader = MetricsReader(get_observability_provider())
    indicator = reader.connector_success_ratio()
    assert indicator.sample_count >= 1
    assert indicator.value == 1.0
    # Audit health also flows through from the same real operations.
    audit_health = reader.required_audit_write_success_ratio()
    assert audit_health.sample_count >= 1
    assert audit_health.value == 1.0


def test_connector_slo_consumes_real_samples(uow, installed_provider):
    _run_successful_syncs(uow)
    obs = ObservabilityService(uow)
    ctx = _obs_ctx()
    obs.ensure_default_slo_definitions(ctx)
    evaluations = {e.slo_key: e for e in obs.evaluate_slos(ctx)}
    connector = evaluations["connector_sync_success"]
    assert connector.sample_count >= 1
    assert connector.observed_value == 1.0
    assert connector.status != "insufficient_data"


def test_zero_samples_remain_insufficient_data(uow, installed_provider):
    # No connector operation performed -> the SLO must honestly report insufficiency.
    obs = ObservabilityService(uow)
    ctx = _obs_ctx()
    obs.ensure_default_slo_definitions(ctx)
    evaluations = {e.slo_key: e for e in obs.evaluate_slos(ctx)}
    connector = evaluations["connector_sync_success"]
    assert connector.sample_count == 0
    assert connector.status == "insufficient_data"
    assert connector.observed_value is None


def test_runtime_call_sites_emit_only_bounded_attributes(uow, installed_provider):
    _run_successful_syncs(uow, count=2)
    emitted_keys: set[str] = set()
    for _name, attrs in list(installed_provider.counters) + list(installed_provider.histograms):
        emitted_keys.update(dict(attrs))
    # Only allowlisted, low-cardinality labels may ever be exported.
    assert emitted_keys, "expected some emitted attributes"
    assert emitted_keys <= ALLOWED_ATTRIBUTES
    # No prohibited high-cardinality / sensitive dimension may appear.
    assert emitted_keys.isdisjoint(DENIED_ATTRIBUTES)


def test_telemetry_provider_failure_does_not_fabricate_healthy_slo(uow):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

        def record_value(self, *a, **k):
            raise RuntimeError("boom")

    set_observability_provider(ExplodingProvider())
    try:
        _run_successful_syncs(uow)  # telemetry export fails, business unaffected
        obs = ObservabilityService(uow)
        ctx = _obs_ctx()
        obs.ensure_default_slo_definitions(ctx)
        evaluations = {e.slo_key: e for e in obs.evaluate_slos(ctx)}
        connector = evaluations["connector_sync_success"]
        # A failing provider captured nothing -> insufficient, never a fake healthy SLO.
        assert connector.status == "insufficient_data"
    finally:
        reset_observability_provider()
