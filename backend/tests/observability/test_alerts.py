"""Alert dedupe + state-transition + service flow tests (Phase 3 Prompt 8)."""

from __future__ import annotations

import pytest

from app.observability.alerts import alert_fingerprint
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.security.context import internal_system_context
from app.security.enums import SecurityRole
from app.security.exceptions import AuthorizationError, SecurityError
from app.services.observability.observability_service import ObservabilityService

TENANT = "novabank"


def _ctx(tenant=TENANT, roles=None):
    return internal_system_context(
        tenant,
        correlation_id="test-corr",
        roles=roles,
    )


def test_fingerprint_is_stable():
    a = alert_fingerprint(source="slo", reason_code="slo_breached", subject="api_availability")
    b = alert_fingerprint(source="slo", reason_code="slo_breached", subject="api_availability")
    assert a == b and len(a) == 32


def test_alert_dedup_and_transitions(uow):
    record, created = uow.alert_events.upsert_open(
        TENANT,
        fingerprint="fp1",
        severity="critical",
        source="slo",
        title="SLO breached",
        reason_code="slo_breached",
    )
    assert created is True
    _, created2 = uow.alert_events.upsert_open(
        TENANT,
        fingerprint="fp1",
        severity="critical",
        source="slo",
        title="SLO breached",
        reason_code="slo_breached",
    )
    assert created2 is False  # deduplicated, no second open alert
    open_alerts = uow.alert_events.list(TENANT, state="open")
    assert len(open_alerts) == 1
    # Acknowledge then resolve.
    row = uow.alert_events.get(TENANT, record.id)
    acked = uow.alert_events.transition(row, new_state="acknowledged", reason="ack")
    assert acked.state == "acknowledged"
    resolved = uow.alert_events.transition(row, new_state="resolved", reason="fixed")
    assert resolved.state == "resolved"
    assert len(resolved.transitions) >= 3


def test_service_acknowledge_requires_manage(uow):
    # Create an open alert directly.
    record, _ = uow.alert_events.upsert_open(
        TENANT,
        fingerprint="fp-ack",
        severity="warning",
        source="slo",
        title="t",
        reason_code="slo_at_risk",
    )
    uow.commit()
    service = ObservabilityService(uow)
    # A role without observability.manage is denied.
    reader_ctx = _ctx(roles=frozenset({SecurityRole.INTEGRATION_OPERATOR}))
    with pytest.raises(AuthorizationError):
        service.acknowledge_alert(reader_ctx, alert_id=record.id)
    # Tenant admin can acknowledge.
    admin_ctx = _ctx(roles=frozenset({SecurityRole.TENANT_ADMIN}))
    acked = service.acknowledge_alert(admin_ctx, alert_id=record.id)
    assert acked.state == "acknowledged"


def test_service_foreign_alert_is_indistinguishable(uow):
    service = ObservabilityService(uow)
    admin_ctx = _ctx(roles=frozenset({SecurityRole.TENANT_ADMIN}))
    with pytest.raises(SecurityError):
        service.acknowledge_alert(admin_ctx, alert_id="nonexistent")


def test_evaluate_slos_opens_alert_and_dedupes(uow):
    provider = InMemoryObservabilityProvider()
    # Force a breach with enough samples (>= min_sample_count of 20):
    # 20 requests, 10 server errors -> 50% 5xx-free ratio (< 0.99).
    for _ in range(10):
        provider.increment(MetricName.HTTP_REQUESTS)
        provider.increment(MetricName.HTTP_SERVER_ERRORS)
    for _ in range(10):
        provider.increment(MetricName.HTTP_REQUESTS)
    set_observability_provider(provider)
    try:
        service = ObservabilityService(uow)
        ctx = _ctx(roles=frozenset({SecurityRole.TENANT_ADMIN}))
        service.evaluate_slos(ctx)
        first_open = uow.alert_events.list(TENANT, state="open")
        service.evaluate_slos(ctx)
        second_open = uow.alert_events.list(TENANT, state="open")
        # Availability SLO breach opens exactly one alert; re-evaluation dedupes.
        avail = [a for a in second_open if a.correlated_slo_key == "api_availability"]
        assert len(avail) == 1
        assert len(second_open) == len(first_open)
    finally:
        reset_observability_provider()
