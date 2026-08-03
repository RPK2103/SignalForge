"""HTTP request telemetry + status-semantics tests (Phase 3 Prompt 8).

Proves the critical rule: expected 401/403 are security-denial telemetry and are
NEVER counted as 5xx server failures, while a genuine 500 is.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.metrics import MetricName, OperationOutcome
from app.observability.middleware import (
    RequestTelemetryMiddleware,
    classify_outcome,
)
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import set_observability_provider
from tests.support.auth import bearer, mint_test_token

TENANT_HEADER = "X-SignalForge-Tenant-ID"


def _admin_headers(tenant="novabank"):
    h = bearer(mint_test_token(roles=("tenant_admin",)))
    h[TENANT_HEADER] = tenant
    return h


def test_health_200_records_normal_request(obs_client):
    client, provider = obs_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert provider.counter_total(MetricName.HTTP_REQUESTS) >= 1
    assert provider.counter_total(MetricName.HTTP_SERVER_ERRORS) == 0


def test_unauthenticated_connectors_is_authentication_denial(obs_client):
    client, provider = obs_client
    resp = client.get("/api/v3/connectors")
    assert resp.status_code == 401
    assert provider.counter_total(MetricName.HTTP_AUTHENTICATION_DENIALS) == 1
    assert provider.counter_total(MetricName.HTTP_SERVER_ERRORS) == 0


def test_unauthenticated_simulate_is_authentication_denial(obs_client):
    client, provider = obs_client
    resp = client.post("/simulate", json={})
    assert resp.status_code == 401
    assert provider.counter_total(MetricName.HTTP_AUTHENTICATION_DENIALS) == 1
    assert provider.counter_total(MetricName.HTTP_SERVER_ERRORS) == 0


def test_unauthorized_role_is_authorization_denial(obs_client):
    client, provider = obs_client
    # executive_reader lacks observability.read -> 403.
    headers = bearer(mint_test_token(roles=("executive_reader",)))
    headers[TENANT_HEADER] = "novabank"
    resp = client.get("/api/v3/observability/summary", headers=headers)
    assert resp.status_code == 403
    assert provider.counter_total(MetricName.HTTP_AUTHORIZATION_DENIALS) == 1
    assert provider.counter_total(MetricName.HTTP_SERVER_ERRORS) == 0


def test_correlation_id_returned_and_sanitized(obs_client):
    client, _ = obs_client
    resp = client.get("/health", headers={"X-Correlation-ID": "a" * 500})
    # Oversized correlation id is replaced by a safe generated one.
    returned = resp.headers.get("X-Correlation-ID")
    assert returned and len(returned) <= 128 and returned != "a" * 500


def test_valid_correlation_id_preserved(obs_client):
    client, _ = obs_client
    resp = client.get("/health", headers={"X-Correlation-ID": "safe-corr-123"})
    assert resp.headers.get("X-Correlation-ID") == "safe-corr-123"


def test_latency_recorded(obs_client):
    client, provider = obs_client
    client.get("/health")
    assert provider.histogram_values(MetricName.HTTP_REQUEST_DURATION)


# -- pure middleware unit tests (genuine 500, 404) ---------------------------
def _standalone_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestTelemetryMiddleware)

    @app.get("/boom")
    def boom():
        raise RuntimeError("genuine failure")

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return app


def test_injected_500_increments_server_error():
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    client = TestClient(_standalone_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert provider.counter_total(MetricName.HTTP_SERVER_ERRORS) == 1
    assert provider.counter_total(MetricName.HTTP_UNHANDLED_EXCEPTIONS) == 1


def test_404_is_client_not_server_error():
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    client = TestClient(_standalone_app(), raise_server_exceptions=False)
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert provider.counter_total(MetricName.HTTP_SERVER_ERRORS) == 0


def test_classify_outcome_matrix():
    assert classify_outcome(200) is OperationOutcome.SUCCESS
    assert classify_outcome(401) is OperationOutcome.AUTHENTICATION_DENIED
    assert classify_outcome(403) is OperationOutcome.AUTHORIZATION_DENIED
    assert classify_outcome(404) is OperationOutcome.CLIENT_ERROR
    assert classify_outcome(422) is OperationOutcome.CLIENT_ERROR
    assert classify_outcome(429) is OperationOutcome.RATE_LIMITED
    assert classify_outcome(500) is OperationOutcome.SERVER_ERROR
    assert classify_outcome(503) is OperationOutcome.SERVER_ERROR


def test_normalized_route_uses_template():
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    client = TestClient(_standalone_app(), raise_server_exceptions=False)
    client.get("/ok")
    # The template (not a raw path with IDs) is used as the route label.
    routes = {
        dict(attrs).get("route")
        for (name, attrs) in provider.counters
        if name == MetricName.HTTP_REQUESTS.value
    }
    assert "/ok" in routes
