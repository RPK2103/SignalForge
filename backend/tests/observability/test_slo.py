"""SLO evaluation tests (Phase 3 Prompt 8)."""

from __future__ import annotations

from app.domain.observability_models import SloStatus
from app.observability.metrics import MetricName
from app.observability.metrics_reader import MetricsReader
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.slo import GTE, LTE, default_slo_definitions, evaluate_slo
from app.services.observability.observability_service import _read_slo_indicator


def test_healthy_when_meets_objective():
    result = evaluate_slo(
        observed_value=0.999,
        sample_count=100,
        objective=0.99,
        comparison=GTE,
        min_sample_count=20,
    )
    assert result.status is SloStatus.HEALTHY


def test_breached_when_far_below():
    result = evaluate_slo(
        observed_value=0.5,
        sample_count=100,
        objective=0.99,
        comparison=GTE,
        min_sample_count=20,
    )
    assert result.status is SloStatus.BREACHED


def test_at_risk_within_margin():
    result = evaluate_slo(
        observed_value=0.985,
        sample_count=100,
        objective=0.99,
        comparison=GTE,
        min_sample_count=20,
    )
    assert result.status is SloStatus.AT_RISK


def test_insufficient_data_below_min_samples():
    result = evaluate_slo(
        observed_value=1.0,
        sample_count=1,
        objective=0.99,
        comparison=GTE,
        min_sample_count=20,
    )
    assert result.status is SloStatus.INSUFFICIENT_DATA


def test_latency_lte_breached():
    result = evaluate_slo(
        observed_value=5000.0,
        sample_count=50,
        objective=1500.0,
        comparison=LTE,
        min_sample_count=20,
    )
    assert result.status is SloStatus.BREACHED


def test_401_403_do_not_reduce_availability():
    """Expected 401/403 must NOT reduce the 5xx-free availability ratio."""
    provider = InMemoryObservabilityProvider()
    # 10 successful requests, 5 auth denials, 3 authz denials, 0 server errors.
    for _ in range(10):
        provider.increment(MetricName.HTTP_REQUESTS, attributes={"status_family": "2xx"})
    for _ in range(5):
        provider.increment(MetricName.HTTP_REQUESTS, attributes={"status_family": "4xx"})
        provider.increment(MetricName.HTTP_AUTHENTICATION_DENIALS)
    for _ in range(3):
        provider.increment(MetricName.HTTP_REQUESTS, attributes={"status_family": "4xx"})
        provider.increment(MetricName.HTTP_AUTHORIZATION_DENIALS)
    reader = MetricsReader(provider)
    indicator = reader.api_5xx_free_ratio()
    # No server errors => ratio is 1.0 despite the denials.
    assert indicator.value == 1.0
    result = evaluate_slo(
        observed_value=indicator.value,
        sample_count=indicator.sample_count,
        objective=0.99,
        comparison=GTE,
        min_sample_count=1,
    )
    assert result.status is SloStatus.HEALTHY


def test_genuine_500_reduces_availability():
    provider = InMemoryObservabilityProvider()
    for _ in range(9):
        provider.increment(MetricName.HTTP_REQUESTS, attributes={"status_family": "2xx"})
    provider.increment(MetricName.HTTP_REQUESTS, attributes={"status_family": "5xx"})
    provider.increment(MetricName.HTTP_SERVER_ERRORS)
    reader = MetricsReader(provider)
    indicator = reader.api_5xx_free_ratio()
    assert indicator.value == 0.9


def test_default_slo_identifiers_are_public_product_metadata():
    """Default SLO identifiers are deterministic product labels, not credentials."""
    specs = default_slo_definitions()
    identifiers = [spec.slo_identifier for spec in specs]
    assert "api_latency_p95" in identifiers
    assert "api_availability" in identifiers
    assert all(isinstance(value, str) and value for value in identifiers)
    # Public contract field name on persisted/API records remains ``slo_key``.
    assert all(hasattr(spec, "slo_identifier") for spec in specs)
    assert not any(hasattr(spec, "slo_key") for spec in specs)


def test_latency_indicator_dispatch_unchanged():
    provider = InMemoryObservabilityProvider()
    for value in (10.0, 20.0, 100.0):
        provider.record_value(MetricName.HTTP_REQUEST_DURATION, value)
    reader = MetricsReader(provider)
    sample = _read_slo_indicator(reader, "api_latency_p95_ms")
    assert sample is not None
    assert sample.sample_count == 3
    assert _read_slo_indicator(reader, "unknown_indicator") is None
