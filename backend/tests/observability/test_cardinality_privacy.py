"""Cardinality + privacy policy tests (Phase 3 Prompt 8)."""

from __future__ import annotations

from app.observability.attributes import (
    ALLOWED_ATTRIBUTES,
    DENIED_ATTRIBUTES,
    TelemetryAttributePolicy,
)
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider


def test_allowlist_and_denylist_are_disjoint():
    assert ALLOWED_ATTRIBUTES.isdisjoint(DENIED_ATTRIBUTES)


def test_denied_keys_dropped():
    policy = TelemetryAttributePolicy()
    clean = policy.sanitize(
        {
            "route": "/api/v3/observability/summary",
            "tenant_id": "tenant-secret",
            "correlation_id": "abc",
            "prompt": "leak me",
            "token": "bearer xyz",
            "email": "a@b.com",
        }
    )
    assert clean == {"route": "/api/v3/observability/summary"}


def test_nested_and_binary_values_dropped():
    policy = TelemetryAttributePolicy()
    clean = policy.sanitize({"outcome": {"nested": 1}, "status_family": b"2xx", "service": "sf"})
    assert clean == {"service": "sf"}


def test_value_length_bounded():
    policy = TelemetryAttributePolicy()
    clean = policy.sanitize({"route": "/x/" + "y" * 500})
    assert len(clean["route"]) <= 64


def test_provider_enforces_policy_on_increment():
    provider = InMemoryObservabilityProvider()
    provider.increment(
        MetricName.HTTP_REQUESTS,
        attributes={"route": "/ok", "tenant_id": "leak", "prompt": "leak"},
    )
    # Only the allowlisted route label survives; no tenant/prompt dimension exists.
    for _name, attrs in provider.counters:
        attr_map = dict(attrs)
        assert "tenant_id" not in attr_map
        assert "prompt" not in attr_map


def test_adversarial_values_under_allowlisted_keys_are_redacted():
    policy = TelemetryAttributePolicy()
    clean = policy.sanitize(
        {
            "model_version": "alice@example.com",
            "fallback_category": "550e8400-e29b-41d4-a716-446655440000",
            "connector_type": "Bearer " + ("a" * 40),
            "operation": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
            "outcome": "success",
            "scenario_kind": "capacity_shift",
        }
    )
    assert clean["model_version"] == "redacted"
    assert clean["fallback_category"] == "redacted"
    assert clean["connector_type"] == "redacted"
    assert clean["operation"] == "redacted"
    # Honest bounded enums pass through unchanged.
    assert clean["outcome"] == "success"
    assert clean["scenario_kind"] == "capacity_shift"
