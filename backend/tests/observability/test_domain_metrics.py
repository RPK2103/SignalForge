"""Domain telemetry recorder tests (Phase 3 Prompt 8)."""

from __future__ import annotations

import pytest

from app.observability import domain
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider


@pytest.fixture
def provider():
    p = InMemoryObservabilityProvider()
    set_observability_provider(p)
    yield p
    reset_observability_provider()


def test_connector_sync_success_and_dedup(provider):
    domain.record_connector_sync(
        connector_type="github",
        outcome="success",
        duration_ms=120.0,
        observed=10,
        accepted=7,
        deduplicated=3,
    )
    assert provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="success") == 1
    assert provider.counter_total(MetricName.CONNECTOR_RECORDS_DEDUPLICATED) == 3
    assert provider.histogram_values(MetricName.CONNECTOR_SYNC_DURATION)


def test_connector_sync_failure(provider):
    domain.record_connector_sync(connector_type="github", outcome="failure")
    assert provider.counter_total(MetricName.CONNECTOR_SYNCS, outcome="failure") == 1


def test_ingestion_lag_recorded(provider):
    domain.record_ingestion_lag(source_type="github", lag_seconds=42.0)
    assert 42.0 in provider.histogram_values(MetricName.CONNECTOR_INGESTION_LAG)


def test_prediction_fallback_and_missing_data(provider):
    domain.record_prediction(
        model_version="v1", outcome="fallback", fallback=True, missing_data=True
    )
    assert provider.counter_total(MetricName.PREDICTION_FALLBACKS) == 1
    assert provider.counter_total(MetricName.PREDICTION_MISSING_DATA) == 1


def test_cos_grounding_and_unsupported(provider):
    domain.record_cos_generation(
        provider_type="deterministic",
        outcome="rejected",
        grounding_failure=True,
        unsupported_claim=True,
        fallback=True,
        fallback_category="grounding",
    )
    assert provider.counter_total(MetricName.COS_GROUNDING_FAILURES) == 1
    assert provider.counter_total(MetricName.COS_UNSUPPORTED_CLAIM_REJECTIONS) == 1
    assert provider.counter_total(MetricName.COS_FALLBACKS) == 1


def test_audit_write_health(provider):
    domain.record_audit_write(required=True, succeeded=True)
    domain.record_audit_write(required=True, succeeded=False, fail_closed=True)
    assert provider.counter_total(MetricName.AUDIT_WRITES_REQUIRED) == 2
    assert provider.counter_total(MetricName.AUDIT_WRITES_SUCCEEDED) == 1
    assert provider.counter_total(MetricName.AUDIT_WRITES_FAILED) == 1
    assert provider.counter_total(MetricName.AUDIT_FAIL_CLOSED_MUTATIONS) == 1


def test_telemetry_failure_never_raises():
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

    set_observability_provider(ExplodingProvider())
    try:
        # Must not raise despite the provider failing.
        domain.record_connector_sync(connector_type="github", outcome="success")
    finally:
        reset_observability_provider()
