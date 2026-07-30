"""Adversarial authorization tests for enterprise ingestion writes (Prompt 7 remediation).

Enterprise ingestion writes are gated by explicit connector permissions at BOTH
the API route and the ``IngestionService`` boundary (deny-by-default):

- data-source configuration -> ``connectors.manage``
- ingestion execution (run start/complete, evidence append) -> ``connectors.sync``

Read-only roles (``executive_reader``, ``security_auditor``, ``intelligence_analyst``)
must never be able to write, and a direct service call without a valid, authorized
:class:`SecurityContext` must fail closed.
"""

from __future__ import annotations

import pytest

from app.api.v3.dependencies import TENANT_HEADER
from app.domain.enterprise_enums import DataSourceType, IngestionRunStatus
from app.security.context import internal_system_context
from app.security.enums import SecurityRole
from app.security.exceptions import AuthorizationError
from app.services.enterprise.enterprise_services import IngestionService
from app.services.enterprise.exceptions import EnterpriseNotFoundError
from tests.support.auth import bearer, mint_test_token

READ_ONLY_ROLES = ["executive_reader", "security_auditor", "intelligence_analyst"]
DATA_SOURCE_BODY = {"source_type": "github", "display_name": "Authz GH"}


def _headers(role: str, *, tenant: str = "novabank") -> dict[str, str]:
    token = mint_test_token(roles=(role,), tenant_selector=tenant)
    headers = bearer(token)
    headers[TENANT_HEADER] = tenant
    return headers


# --------------------------------------------------------------------------- #
# Route-level enforcement                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", READ_ONLY_ROLES)
def test_data_source_registration_denied_for_read_roles(client, role):
    resp = client.post("/api/v3/data-sources", headers=_headers(role), json=DATA_SOURCE_BODY)
    assert resp.status_code == 403


@pytest.mark.parametrize("role", READ_ONLY_ROLES)
def test_ingestion_run_start_denied_for_read_roles(client, role):
    resp = client.post(
        "/api/v3/ingestion-runs", headers=_headers(role), json={"data_source_id": "ds_x"}
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("role", READ_ONLY_ROLES)
def test_evidence_append_denied_for_read_roles(client, role):
    body = {
        "data_source_id": "ds_x",
        "source_record_id": "rec-1",
        "signal_type": "commit",
        "subject_type": "repository",
        "subject_id": "repo-1",
        "event_time": "2026-02-01T09:00:00Z",
        "payload": {"kind": "commit", "sha": "abc"},
    }
    resp = client.post("/api/v3/evidence-signals", headers=_headers(role), json=body)
    assert resp.status_code == 403


def test_integration_operator_can_register_and_sync(client):
    reg = client.post(
        "/api/v3/data-sources", headers=_headers("integration_operator"), json=DATA_SOURCE_BODY
    )
    assert reg.status_code == 201
    ds_id = reg.json()["data_source_id"]
    run = client.post(
        "/api/v3/ingestion-runs",
        headers=_headers("integration_operator"),
        json={"data_source_id": ds_id},
    )
    assert run.status_code == 201


def test_tenant_admin_can_register(client):
    reg = client.post(
        "/api/v3/data-sources", headers=_headers("tenant_admin"), json=DATA_SOURCE_BODY
    )
    assert reg.status_code == 201


def test_write_requires_token(client):
    # No bearer at all -> authentication failure (fail closed) before any authz.
    resp = client.post(
        "/api/v3/data-sources",
        headers={"Authorization": "", TENANT_HEADER: "novabank"},
        json=DATA_SOURCE_BODY,
    )
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Service-layer enforcement (no route in front of it)                          #
# --------------------------------------------------------------------------- #
def _ctx(tenant: str, role: SecurityRole):
    return internal_system_context(tenant, correlation_id="t", roles=frozenset({role}))


def test_service_denies_without_context(uow):
    svc = IngestionService(uow)
    with pytest.raises(AuthorizationError):
        svc.register_data_source(None, source_type=DataSourceType.GITHUB, display_name="X")


def test_service_denies_read_role_context(uow):
    svc = IngestionService(uow)
    ctx = _ctx("novabank", SecurityRole.EXECUTIVE_READER)
    with pytest.raises(AuthorizationError):
        svc.register_data_source(ctx, source_type=DataSourceType.GITHUB, display_name="X")


def test_service_start_run_denied_for_read_role(uow):
    svc = IngestionService(uow)
    ctx = _ctx("novabank", SecurityRole.INTELLIGENCE_ANALYST)
    with pytest.raises(AuthorizationError):
        svc.start_run(ctx, data_source_id="ds_x")


def test_service_allows_integration_operator(uow):
    svc = IngestionService(uow)
    ctx = _ctx("novabank", SecurityRole.INTEGRATION_OPERATOR)
    ds = svc.register_data_source(ctx, source_type=DataSourceType.GITHUB, display_name="X")
    run = svc.start_run(ctx, data_source_id=ds.data_source_id)
    assert run.ingestion_run_id


def test_service_cross_tenant_run_is_not_found(uow):
    svc = IngestionService(uow)
    ctx_a = _ctx("tenant-a", SecurityRole.INTEGRATION_OPERATOR)
    ds = svc.register_data_source(ctx_a, source_type=DataSourceType.GITHUB, display_name="A")
    run = svc.start_run(ctx_a, data_source_id=ds.data_source_id)
    ctx_b = _ctx("tenant-b", SecurityRole.INTEGRATION_OPERATOR)
    with pytest.raises(EnterpriseNotFoundError):
        svc.complete_run(
            ctx_b, ingestion_run_id=run.ingestion_run_id, status=IngestionRunStatus.SUCCEEDED
        )
