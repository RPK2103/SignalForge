"""Ingestion pipeline: sync, idempotency, checkpoints, dead letters, tenants."""

from __future__ import annotations

import pytest

from app.connectors.config import hash_connector_config, validate_connector_config
from app.connectors.fake import FakeGitHubConnector, make_repo_page
from app.connectors.github.normalize import normalize_issue, normalize_pull_request
from app.connectors.orchestrator import IngestionOrchestrator, redact_payload
from app.connectors.protocol import ConnectorCheckpointCursor, ConnectorContext, ConnectorPage
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    DataSourceStatus,
    DataSourceType,
    IngestionReceiptOutcome,
    IngestionRunStatus,
    PermissionClassification,
)
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash


def _register_github(uow, ctx: TenantContext, name: str = "gh-demo") -> dm.DataSource:
    config = validate_connector_config(
        "github",
        {
            "owner": "octocat",
            "repository": "Hello-World",
            "enabled_streams": ["repository", "issues", "pull_requests"],
            "page_size": 30,
            "maximum_pages": 2,
        },
    )
    source = dm.DataSource(
        data_source_id=build_entity_id("ds", ctx.tenant_id, "github", name),
        tenant_id=ctx.tenant_id,
        source_type=DataSourceType.GITHUB,
        display_name=name,
        credential_reference="public://none",
        connector_config=config,
        connector_config_schema_version="1",
        connector_config_hash=hash_connector_config(config),
        status=DataSourceStatus.REGISTERED,
        permission_classification=PermissionClassification.PUBLIC,
    )
    uow.data_sources.add_data_source(ctx, source)
    uow.commit()
    return source


def _issue_page(
    context: ConnectorContext, issue_id: int = 10, updated: str = "2024-06-01T00:00:00Z"
):
    raw = {
        "id": issue_id,
        "number": issue_id,
        "title": f"Issue {issue_id}",
        "state": "open",
        "updated_at": updated,
        "created_at": updated,
        "labels": [],
        "user": {"login": "octocat"},
    }
    event = normalize_issue(
        tenant_id=context.tenant.tenant_id,
        data_source_id=context.data_source_id,
        raw=raw,
    )
    return ConnectorPage(
        stream_name="issues",
        records=[raw],
        normalized_events=[event],
        next_checkpoint=ConnectorCheckpointCursor(
            payload={"page": 1, "completed": True},
            high_watermark_time=event.event_time,
            high_watermark_source_id=event.source_record_id,
        ),
        has_more=False,
        request_count=1,
    )


def test_initial_and_incremental_sync_idempotent(uow, tenant_a):
    source = _register_github(uow, tenant_a)
    ctx_conn = ConnectorContext(
        tenant=tenant_a,
        data_source_id=source.data_source_id,
        correlation_id="run1",
    )
    fake = FakeGitHubConnector(
        pages={
            "repository": [make_repo_page(ctx_conn)],
            "issues": [_issue_page(ctx_conn)],
            "pull_requests": [],
        }
    )
    orch = IngestionOrchestrator(uow, connector=fake)
    first = orch.sync_data_source(
        tenant_a,
        source.data_source_id,
        streams=["repository", "issues"],
        maximum_pages=1,
    )
    assert first.status == IngestionRunStatus.SUCCEEDED
    assert first.counters.created >= 2
    assert first.counters.dead_lettered == 0

    evidence_page = uow.evidence_signals.list_by_source(
        tenant_a, data_source_id=source.data_source_id, limit=100
    )
    first_count = evidence_page.total

    fake2 = FakeGitHubConnector(
        pages={
            "repository": [make_repo_page(ctx_conn)],
            "issues": [_issue_page(ctx_conn)],
            "pull_requests": [],
        }
    )
    orch2 = IngestionOrchestrator(uow, connector=fake2)
    second = orch2.sync_data_source(
        tenant_a,
        source.data_source_id,
        streams=["repository", "issues"],
        maximum_pages=1,
    )
    assert second.status == IngestionRunStatus.SUCCEEDED
    assert second.counters.deduplicated >= 2
    assert second.counters.created == 0

    evidence_page2 = uow.evidence_signals.list_by_source(
        tenant_a, data_source_id=source.data_source_id, limit=100
    )
    assert evidence_page2.total == first_count

    receipts = uow.ingestion_receipts.list_for_run(
        tenant_a, ingestion_run_id=second.ingestion_run_id, limit=100
    )
    assert receipts.total >= 2
    assert all(
        r.outcome
        in {
            IngestionReceiptOutcome.DEDUPLICATED,
            IngestionReceiptOutcome.PROJECTED,
            IngestionReceiptOutcome.CREATED,
        }
        for r in receipts.items
    )

    ckpts = uow.connector_checkpoints.list_for_source(
        tenant_a, data_source_id=source.data_source_id, limit=10
    )
    assert ckpts.total >= 2


def test_changed_payload_creates_new_evidence(uow, tenant_a):
    source = _register_github(uow, tenant_a, name="gh-change")
    ctx_conn = ConnectorContext(
        tenant=tenant_a, data_source_id=source.data_source_id, correlation_id="c"
    )
    fake = FakeGitHubConnector(
        pages={"repository": [make_repo_page(ctx_conn, updated_at="2024-01-01T00:00:00Z")]}
    )
    IngestionOrchestrator(uow, connector=fake).sync_data_source(
        tenant_a, source.data_source_id, streams=["repository"]
    )
    fake2 = FakeGitHubConnector(
        pages={"repository": [make_repo_page(ctx_conn, updated_at="2024-06-01T00:00:00Z")]}
    )
    result = IngestionOrchestrator(uow, connector=fake2).sync_data_source(
        tenant_a, source.data_source_id, streams=["repository"]
    )
    assert result.counters.created == 1
    page = uow.evidence_signals.list_by_source(
        tenant_a, data_source_id=source.data_source_id, limit=10
    )
    assert page.total == 2


def test_dead_letter_on_unsupported_event(uow, tenant_a):
    source = _register_github(uow, tenant_a, name="gh-dl")
    ctx_conn = ConnectorContext(
        tenant=tenant_a, data_source_id=source.data_source_id, correlation_id="dl"
    )
    bad_event_page = make_repo_page(ctx_conn)
    bad_event = bad_event_page.normalized_events[0].model_copy(
        update={"event_type": "github.unknown.snapshot"}
    )
    bad_page = ConnectorPage(
        stream_name="repository",
        records=bad_event_page.records,
        normalized_events=[bad_event],
        next_checkpoint=bad_event_page.next_checkpoint,
        has_more=False,
        request_count=1,
    )
    fake = FakeGitHubConnector(pages={"repository": [bad_page]})
    result = IngestionOrchestrator(uow, connector=fake).sync_data_source(
        tenant_a, source.data_source_id, streams=["repository"]
    )
    assert result.counters.dead_lettered == 1
    assert result.status == IngestionRunStatus.PARTIAL
    dls = uow.ingestion_dead_letters.list_for_run(
        tenant_a, ingestion_run_id=result.ingestion_run_id, limit=10
    )
    assert dls.total == 1
    ckpt = uow.connector_checkpoints.get(
        tenant_a, data_source_id=source.data_source_id, stream_name="repository"
    )
    assert ckpt is not None


def test_redact_payload_strips_secrets():
    redacted = redact_payload({"title": "ok", "token": "secret", "nested": {"password": "x"}})
    assert redacted["token"] == "[redacted]"
    assert redacted["nested"]["password"] == "[redacted]"
    assert redacted["title"] == "ok"


def test_tenant_isolation_checkpoints(uow, tenant_a, tenant_b):
    source_a = _register_github(uow, tenant_a, name="a")
    source_b = _register_github(uow, tenant_b, name="b")
    ctx_a = ConnectorContext(
        tenant=tenant_a, data_source_id=source_a.data_source_id, correlation_id="a"
    )
    ctx_b = ConnectorContext(
        tenant=tenant_b, data_source_id=source_b.data_source_id, correlation_id="b"
    )
    IngestionOrchestrator(
        uow, connector=FakeGitHubConnector(pages={"repository": [make_repo_page(ctx_a)]})
    ).sync_data_source(tenant_a, source_a.data_source_id, streams=["repository"])
    IngestionOrchestrator(
        uow, connector=FakeGitHubConnector(pages={"repository": [make_repo_page(ctx_b)]})
    ).sync_data_source(tenant_b, source_b.data_source_id, streams=["repository"])

    assert (
        uow.connector_checkpoints.list_for_source(
            tenant_a, data_source_id=source_a.data_source_id
        ).total
        >= 1
    )
    assert (
        uow.connector_checkpoints.list_for_source(
            tenant_a, data_source_id=source_b.data_source_id
        ).total
        == 0
    )
    assert uow.data_sources.get_data_source(tenant_a, source_b.data_source_id) is None


def test_checkpoint_version_conflict(uow, tenant_a):
    source = _register_github(uow, tenant_a, name="ckpt")
    ckpt = dm.ConnectorCheckpoint(
        connector_checkpoint_id=build_entity_id(
            "ckpt", tenant_a.tenant_id, source.data_source_id, "repository"
        ),
        tenant_id=tenant_a.tenant_id,
        data_source_id=source.data_source_id,
        stream_name="repository",
        cursor_payload={"page": 1},
        cursor_hash=snapshot_hash({"page": 1}),
        version=1,
    )
    uow.connector_checkpoints.upsert(tenant_a, ckpt)
    uow.commit()
    updated = ckpt.model_copy(
        update={"cursor_payload": {"page": 2}, "cursor_hash": snapshot_hash({"page": 2})}
    )
    uow.connector_checkpoints.upsert(tenant_a, updated, expected_version=1)
    uow.commit()
    with pytest.raises(Exception):
        uow.connector_checkpoints.upsert(tenant_a, updated, expected_version=1)


def test_manual_repo_not_overwritten_by_connector(uow, tenant_a):
    source = _register_github(uow, tenant_a, name="manual-prec")
    manual = dm.Repository(
        repository_id=build_entity_id("repo", tenant_a.tenant_id, "github", "octocat/Hello-World"),
        tenant_id=tenant_a.tenant_id,
        provider=DataSourceType.GITHUB,
        external_reference="octocat/Hello-World",
        name="Manual Name",
        source_precedence="manual",
    )
    uow.delivery.add_repository(tenant_a, manual)
    uow.commit()
    ctx_conn = ConnectorContext(
        tenant=tenant_a, data_source_id=source.data_source_id, correlation_id="m"
    )
    IngestionOrchestrator(
        uow, connector=FakeGitHubConnector(pages={"repository": [make_repo_page(ctx_conn)]})
    ).sync_data_source(tenant_a, source.data_source_id, streams=["repository"])
    refreshed = uow.delivery.get_repository(tenant_a, manual.repository_id)
    assert refreshed.name == "Manual Name"
    assert refreshed.source_precedence == "manual"
    assert refreshed.last_evidence_signal_id is not None


def test_pull_request_projection(uow, tenant_a):
    source = _register_github(uow, tenant_a, name="pr-proj")
    raw = {
        "id": 99,
        "number": 7,
        "title": "Add feature",
        "state": "open",
        "draft": False,
        "user": {"login": "octocat"},
        "updated_at": "2024-05-01T00:00:00Z",
        "created_at": "2024-04-01T00:00:00Z",
    }
    event = normalize_pull_request(
        tenant_id=tenant_a.tenant_id, data_source_id=source.data_source_id, raw=raw
    )
    page = ConnectorPage(
        stream_name="pull_requests",
        records=[raw],
        normalized_events=[event],
        next_checkpoint=ConnectorCheckpointCursor(
            payload={"page": 1, "completed": True},
            high_watermark_time=event.event_time,
            high_watermark_source_id=event.source_record_id,
        ),
        has_more=False,
        request_count=1,
    )
    IngestionOrchestrator(
        uow, connector=FakeGitHubConnector(pages={"pull_requests": [page]})
    ).sync_data_source(tenant_a, source.data_source_id, streams=["pull_requests"])
    pr = uow.pull_requests.get_by_external(tenant_a, provider="github", external_id="99")
    assert pr is not None
    assert pr.number == 7
    assert pr.title == "Add feature"
