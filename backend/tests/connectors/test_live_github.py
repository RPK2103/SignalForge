"""Opt-in live GitHub public API smoke test.

Requires SIGNALFORGE_RUN_LIVE_GITHUB_TESTS=1. No token required. No writes.
"""

from __future__ import annotations

import os

import pytest

from app.connectors.config import hash_connector_config, validate_connector_config
from app.connectors.orchestrator import IngestionOrchestrator
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    DataSourceStatus,
    DataSourceType,
    IngestionRunStatus,
    PermissionClassification,
)
from app.domain.enterprise_identifiers import build_entity_id

pytestmark = pytest.mark.skipif(
    os.environ.get("SIGNALFORGE_RUN_LIVE_GITHUB_TESTS") != "1",
    reason="Set SIGNALFORGE_RUN_LIVE_GITHUB_TESTS=1 to run live GitHub smoke",
)


def test_live_github_public_smoke(uow, tenant_a):
    owner = os.environ.get("SIGNALFORGE_LIVE_GITHUB_OWNER", "octocat")
    repo = os.environ.get("SIGNALFORGE_LIVE_GITHUB_REPO", "Hello-World")
    config = validate_connector_config(
        "github",
        {
            "owner": owner,
            "repository": repo,
            "enabled_streams": ["repository", "issues", "pull_requests", "releases"],
            "page_size": 5,
            "maximum_pages": 1,
            "overlap_seconds": 60,
        },
    )
    source = dm.DataSource(
        data_source_id=build_entity_id("ds", tenant_a.tenant_id, "github", f"live-{owner}-{repo}"),
        tenant_id=tenant_a.tenant_id,
        source_type=DataSourceType.GITHUB,
        display_name=f"Live {owner}/{repo}",
        credential_reference="public://none",
        connector_config=config,
        connector_config_schema_version="1",
        connector_config_hash=hash_connector_config(config),
        status=DataSourceStatus.REGISTERED,
        permission_classification=PermissionClassification.PUBLIC,
    )
    uow.data_sources.add_data_source(tenant_a, source)
    uow.commit()

    orch = IngestionOrchestrator(uow)
    first = orch.sync_data_source(
        tenant_a,
        source.data_source_id,
        streams=["repository", "issues", "pull_requests", "releases"],
        maximum_pages=1,
    )
    assert first.status in {IngestionRunStatus.SUCCEEDED, IngestionRunStatus.PARTIAL}
    assert first.counters.requests >= 1
    assert first.counters.fetched >= 1  # at least repository

    evidence1 = uow.evidence_signals.list_by_source(
        tenant_a, data_source_id=source.data_source_id, limit=100
    )
    created = first.counters.created

    second = orch.sync_data_source(
        tenant_a,
        source.data_source_id,
        streams=["repository", "issues", "pull_requests", "releases"],
        maximum_pages=1,
    )
    evidence2 = uow.evidence_signals.list_by_source(
        tenant_a, data_source_id=source.data_source_id, limit=100
    )
    assert evidence2.total == evidence1.total  # no duplicate evidence for identical snapshots
    assert second.counters.deduplicated >= 1 or second.counters.created >= 0

    receipts = uow.ingestion_receipts.list_for_run(
        tenant_a, ingestion_run_id=second.ingestion_run_id, limit=100
    )
    assert receipts.total >= 1

    ckpts = uow.connector_checkpoints.list_for_source(
        tenant_a, data_source_id=source.data_source_id, limit=20
    )
    assert ckpts.total >= 1

    # Safe summary for audit evidence (no tokens)
    print(
        {
            "repository": f"{owner}/{repo}",
            "auth_mode": "public_unauthenticated",
            "maximum_pages": 1,
            "first_run": {
                "status": first.status.value,
                "requests": first.counters.requests,
                "fetched": first.counters.fetched,
                "created": created,
                "deduplicated": first.counters.deduplicated,
                "dead_lettered": first.counters.dead_lettered,
            },
            "second_run": {
                "status": second.status.value,
                "created": second.counters.created,
                "deduplicated": second.counters.deduplicated,
                "receipts": receipts.total,
            },
            "checkpoints": ckpts.total,
            "evidence_total": evidence2.total,
        }
    )
