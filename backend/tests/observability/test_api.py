"""Protected observability API tests (Phase 3 Prompt 8)."""

from __future__ import annotations

from tests.support.auth import bearer, mint_test_token

TENANT_HEADER = "X-SignalForge-Tenant-ID"


def _headers(roles, tenant="novabank"):
    h = bearer(mint_test_token(roles=roles))
    h[TENANT_HEADER] = tenant
    return h


def test_summary_requires_authentication(obs_client):
    client, _ = obs_client
    assert client.get("/api/v3/observability/summary").status_code == 401


def test_summary_forbidden_without_permission(obs_client):
    client, _ = obs_client
    resp = client.get("/api/v3/observability/summary", headers=_headers(("executive_reader",)))
    assert resp.status_code == 403


def test_summary_allowed_for_admin(obs_client):
    client, _ = obs_client
    resp = client.get("/api/v3/observability/summary", headers=_headers(("tenant_admin",)))
    assert resp.status_code == 200
    body = resp.json()
    assert "http" in body and "slo_states" in body


def test_ai_quality_read_role_separation(obs_client):
    client, _ = obs_client
    # integration_operator has observability.read but NOT ai_quality.read.
    resp = client.get(
        "/api/v3/observability/ai-quality/runs", headers=_headers(("integration_operator",))
    )
    assert resp.status_code == 403
    # intelligence_analyst has ai_quality.read but NOT observability.read.
    resp2 = client.get("/api/v3/observability/summary", headers=_headers(("intelligence_analyst",)))
    assert resp2.status_code == 403
    resp3 = client.get(
        "/api/v3/observability/ai-quality/runs", headers=_headers(("intelligence_analyst",))
    )
    assert resp3.status_code == 200


def test_run_release_evaluation_and_read_back(obs_client):
    client, _ = obs_client
    run = client.post(
        "/api/v3/observability/ai-quality/evaluate", headers=_headers(("tenant_admin",))
    )
    assert run.status_code == 200
    body = run.json()
    assert body["release_gate_passed"] is True
    assert body["critical_violations"] == 0
    runs = client.get("/api/v3/observability/ai-quality/runs", headers=_headers(("tenant_admin",)))
    assert runs.status_code == 200
    assert len(runs.json()) >= 1
    detail = client.get(
        f"/api/v3/observability/ai-quality/runs/{body['id']}",
        headers=_headers(("tenant_admin",)),
    )
    assert detail.status_code == 200
    assert detail.json()["run"]["id"] == body["id"]


def test_evaluate_forbidden_for_read_only_role(obs_client):
    client, _ = obs_client
    # security_auditor has ai_quality.read but not ai_quality.evaluate.
    resp = client.post(
        "/api/v3/observability/ai-quality/evaluate", headers=_headers(("security_auditor",))
    )
    assert resp.status_code == 403


def test_unknown_run_is_404(obs_client):
    client, _ = obs_client
    resp = client.get(
        "/api/v3/observability/ai-quality/runs/does-not-exist",
        headers=_headers(("tenant_admin",)),
    )
    assert resp.status_code == 404
