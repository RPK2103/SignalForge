"""Read-only connector API tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_engine
from app.main import app


@pytest.fixture
def client(migrated_db: str) -> Generator[TestClient, None, None]:
    os.environ["DATABASE_URL"] = migrated_db
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()


def test_list_connectors_no_secrets(client: TestClient):
    # connectors list does not require tenant (capability catalog)
    resp = client.get("/api/v3/connectors")
    assert resp.status_code == 200
    body = resp.json()
    keys = {item["connector_key"] for item in body}
    assert "github" in keys
    assert "jira" in keys
    assert all("token" not in str(item).lower() or "supports" in str(item).lower() for item in body)
    github = next(i for i in body if i["connector_key"] == "github")
    assert github["operational"] is True
    jira = next(i for i in body if i["connector_key"] == "jira")
    assert jira["operational"] is False


def test_register_rejects_raw_token_config(client: TestClient):
    # Construct dynamically so no full github_pat_* literal exists in source for Gitleaks.
    fake_pat = "github" + "_pat_" + ("x" * 40)
    headers = {"X-SignalForge-Tenant-ID": "tenant-a"}
    resp = client.post(
        "/api/v3/data-sources",
        headers=headers,
        json={
            "source_type": "github",
            "display_name": "bad",
            "credential_reference": fake_pat,
            "connector_config": {
                "owner": "octocat",
                "repository": "Hello-World",
                "enabled_streams": ["repository"],
            },
        },
    )
    assert resp.status_code == 422


def test_checkpoint_and_freshness_tenant_404(client: TestClient, uow, tenant_a):
    from app.connectors.config import hash_connector_config, validate_connector_config
    from app.domain import enterprise_models as dm
    from app.domain.enterprise_enums import DataSourceType, PermissionClassification
    from app.domain.enterprise_identifiers import build_entity_id

    config = validate_connector_config(
        "github",
        {
            "owner": "octocat",
            "repository": "Hello-World",
            "enabled_streams": ["repository"],
            "page_size": 10,
        },
    )
    source = dm.DataSource(
        data_source_id=build_entity_id("ds", tenant_a.tenant_id, "github", "api-src"),
        tenant_id=tenant_a.tenant_id,
        source_type=DataSourceType.GITHUB,
        display_name="api-src",
        credential_reference="env://SIGNALFORGE_GITHUB_TOKEN",
        connector_config=config,
        connector_config_schema_version="1",
        connector_config_hash=hash_connector_config(config),
        permission_classification=PermissionClassification.PUBLIC,
    )
    uow.data_sources.add_data_source(tenant_a, source)
    uow.commit()

    headers = {"X-SignalForge-Tenant-ID": "tenant-a"}
    ok = client.get(f"/api/v3/data-sources/{source.data_source_id}/freshness", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["has_credential_reference"] is True
    assert "credential_reference" not in ok.json() or ok.json().get("credential_reference") is None

    other = client.get(
        f"/api/v3/data-sources/{source.data_source_id}/freshness",
        headers={"X-SignalForge-Tenant-ID": "tenant-b"},
    )
    assert other.status_code == 404
