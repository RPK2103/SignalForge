"""API-surface security tests: 401/403/headers/tenant selection (Prompt 7)."""

from __future__ import annotations

from tests.support.auth import bearer, mint_test_token

TENANT_HEADER = "X-SignalForge-Tenant-ID"


def _headers(roles=("tenant_admin",), tenant="novabank", selector=None):
    token = mint_test_token(roles=roles, tenant_selector=selector)
    h = bearer(token)
    if tenant is not None:
        h[TENANT_HEADER] = tenant
    return h


# -- public health -----------------------------------------------------------
def test_root_is_public(client):
    assert client.get("/").status_code == 200


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


# -- authentication ----------------------------------------------------------
def test_protected_route_requires_token(client):
    resp = client.get("/api/v3/connectors")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"
    # No token material echoed back.
    assert "Authorization" not in resp.text


def test_malformed_bearer_rejected(client):
    resp = client.get("/api/v3/connectors", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_valid_token_reaches_protected_route(client):
    resp = client.get("/api/v3/connectors", headers=bearer(mint_test_token()))
    assert resp.status_code == 200


def test_correlation_id_header_present(client):
    resp = client.get("/api/v3/connectors", headers=bearer(mint_test_token()))
    assert resp.headers.get("X-Correlation-ID")


# -- authorization -----------------------------------------------------------
def test_audit_read_forbidden_without_permission(client):
    # executive_reader lacks security.audit.read -> 403.
    resp = client.get(
        "/api/v3/security/audit-events", headers=_headers(roles=("executive_reader",))
    )
    assert resp.status_code == 403


def test_audit_read_allowed_for_admin(client):
    resp = client.get("/api/v3/security/audit-events", headers=_headers(roles=("tenant_admin",)))
    assert resp.status_code == 200


def test_missing_tenant_selector_is_bad_request(client):
    # No X-SignalForge-Tenant-ID header and no selector claim, wildcard membership
    # is ambiguous -> tenant context required.
    resp = client.get("/api/v3/security/audit-events", headers=bearer(mint_test_token()))
    assert resp.status_code == 400


# -- security headers --------------------------------------------------------
def test_security_headers_present(client):
    resp = client.get("/api/v3/connectors", headers=bearer(mint_test_token()))
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "frame-ancestors" in resp.headers.get("Content-Security-Policy", "")
    assert "no-store" in resp.headers.get("Cache-Control", "")
