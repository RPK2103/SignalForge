"""Audit regression tests for Prompt 2 security and reliability gaps."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.connectors.config import reject_secret_keys, validate_connector_config
from app.connectors.credentials import (
    EnvironmentCredentialResolver,
    validate_credential_reference,
)
from app.connectors.errors import ConnectorError
from app.connectors.github.client import GitHubHttpClient, parse_link_header
from app.connectors.github.connector import GitHubConnector
from app.connectors.github.normalize import normalize_pull_request
from app.connectors.orchestrator import redact_payload
from app.connectors.protocol import ConnectorCheckpointCursor, ConnectorContext, ConnectorRequest
from app.connectors.retry import FakeClock, FakeRandom, FakeSleeper, RetryExecutor, RetryPolicy
from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import ConnectorErrorCategory
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseConflictError
from app.services.persistence.snapshot_service import snapshot_hash


@pytest.mark.parametrize(
    "reference",
    [
        "env://PATH",
        "env://USERNAME",
        "env://HOME",
        "env://AWS_SECRET_ACCESS_KEY",
        "env://signalforge_github_token",  # lowercase rejected
    ],
)
def test_env_credential_rejects_non_allowlisted_vars(reference: str, monkeypatch):
    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setenv("USERNAME", "audit-user")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-resolve")
    with pytest.raises(ConnectorError) as exc:
        validate_credential_reference(reference)
    assert exc.value.category == ConnectorErrorCategory.INVALID_CONFIGURATION
    with pytest.raises(ConnectorError):
        EnvironmentCredentialResolver().resolve(reference)


def test_env_credential_allowlists_signalforge_prefix(monkeypatch):
    monkeypatch.setenv("SIGNALFORGE_GITHUB_TOKEN", "audit-sentinel-token-value")
    resolved = EnvironmentCredentialResolver().resolve("env://SIGNALFORGE_GITHUB_TOKEN")
    assert resolved.token == "audit-sentinel-token-value"
    assert "audit-sentinel-token-value" not in repr(resolved)
    assert "audit-sentinel-token-value" not in str(resolved)


@pytest.mark.parametrize(
    "owner,repo",
    [
        ("octo/cat", "Hello-World"),
        ("octocat", "Hello/World"),
        ("octocat", "Hello%2FWorld"),
        ("octocat", "Hello\\World"),
        ("..", "Hello-World"),
        ("octocat", ".."),
        ("octocat", "."),
        ("https://evil.com", "x"),
        ("octocat", "repo?x=1"),
        ("octocat", "repo#frag"),
        ("", "Hello-World"),
        ("octocat", ""),
        ("a" * 80, "Hello-World"),
    ],
)
def test_github_owner_repo_reject_path_injection(owner: str, repo: str):
    with pytest.raises((ConnectorError, ValueError, Exception)):
        validate_connector_config(
            "github",
            {"owner": owner, "repository": repo, "enabled_streams": ["repository"]},
        )


def test_link_header_cross_host_not_followed_as_request_url():
    """Pagination uses page numbers; Link next URL must not become the request target."""
    links = parse_link_header(
        '<https://evil.example/steal>; rel="next", '
        '<https://api.github.com/repos/o/r/pulls?page=2>; rel="last"'
    )
    assert links["next"].startswith("https://evil.example")
    # Client constructs official paths; page_from_link only parses query page ints.
    assert GitHubHttpClient.page_from_link(links["next"]) is None


def test_nested_secret_keys_rejected():
    with pytest.raises(ConnectorError):
        reject_secret_keys({"meta": {"api_key": "x"}})
    with pytest.raises(ConnectorError):
        reject_secret_keys({"items": [{"Authorization": "Bearer x"}]})


def test_redact_payload_recursive_case_variants_and_arrays():
    payload = {
        "Token": "abc",
        "nested": {"PASSWORD": "x", "ok": "keep"},
        "list": [{"access_token": "y"}, {"title": "z"}],
        "Authorization": "Bearer abc",
        "connection_string": "Server=x;Password=y",
    }
    redacted = redact_payload(payload)
    assert redacted["Token"] == "[redacted]"
    assert redacted["nested"]["PASSWORD"] == "[redacted]"
    assert redacted["nested"]["ok"] == "keep"
    assert redacted["list"][0]["access_token"] == "[redacted]"
    assert redacted["list"][1]["title"] == "z"
    assert redacted["Authorization"] == "[redacted]"
    assert redacted["connection_string"] == "[redacted]"
    assert "Bearer abc" not in str(redacted)


def test_equal_timestamp_records_not_skipped_by_since_filter():
    """Records sharing updated_at with the high-watermark must remain eligible."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "host": request.url.host})
        assert request.url.host == "api.github.com"
        body = [
            {
                "id": 1,
                "number": 1,
                "title": "A",
                "state": "open",
                "updated_at": "2024-06-01T12:00:00Z",
                "created_at": "2024-06-01T12:00:00Z",
                "user": {"login": "a"},
            },
            {
                "id": 2,
                "number": 2,
                "title": "B",
                "state": "open",
                "updated_at": "2024-06-01T12:00:00Z",
                "created_at": "2024-06-01T12:00:00Z",
                "user": {"login": "b"},
            },
        ]
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    executor = RetryExecutor(
        RetryPolicy(max_attempts=1, jitter_ratio=0.0),
        clock=clock,
        sleeper=sleeper,
        random_source=FakeRandom([0.0]),
    )
    connector = GitHubConnector(transport=transport, retry_executor=executor, clock=clock)
    ctx = ConnectorContext(
        tenant=TenantContext.require("tenant-a"),
        data_source_id="ds1",
        correlation_id="eq-ts",
    )
    hw = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    page = connector.fetch_page(
        ctx,
        {
            "owner": "octocat",
            "repository": "Hello-World",
            "enabled_streams": ["pull_requests"],
            "page_size": 30,
            "overlap_seconds": 0,
        },
        ConnectorRequest(
            stream_name="pull_requests",
            page_size=30,
            overlap_seconds=0,
            checkpoint=ConnectorCheckpointCursor(
                payload={"page": 1},
                high_watermark_time=hw,
                high_watermark_source_id="github:pr:1",
            ),
        ),
    )
    ids = {e.source_record_id for e in page.normalized_events}
    assert ids == {"github:pr:1", "github:pr:2"}


def test_http_status_matrix_non_retryable_and_retryable():
    cases = [
        (400, ConnectorErrorCategory.INVALID_CONFIGURATION, False),
        (401, ConnectorErrorCategory.AUTHENTICATION_ERROR, False),
        (403, ConnectorErrorCategory.PERMISSION_DENIED, False),
        (404, ConnectorErrorCategory.REPOSITORY_NOT_FOUND, False),
        (409, ConnectorErrorCategory.INVALID_CONFIGURATION, False),
        (422, ConnectorErrorCategory.INVALID_CONFIGURATION, False),
        (429, ConnectorErrorCategory.RATE_LIMITED, True),
        (500, ConnectorErrorCategory.PROVIDER_UNAVAILABLE, True),
        (502, ConnectorErrorCategory.PROVIDER_UNAVAILABLE, True),
        (503, ConnectorErrorCategory.PROVIDER_UNAVAILABLE, True),
    ]
    for status, category, retryable in cases:

        def handler(request: httpx.Request, status=status) -> httpx.Response:
            return httpx.Response(status, json={"message": "err"})

        clock = FakeClock()
        sleeper = FakeSleeper(clock)
        executor = RetryExecutor(
            RetryPolicy(max_attempts=2 if retryable else 1, jitter_ratio=0.0),
            clock=clock,
            sleeper=sleeper,
            random_source=FakeRandom([0.0]),
        )
        transport = httpx.MockTransport(handler)
        client = GitHubHttpClient(transport=transport, retry_executor=executor, clock=clock)
        try:
            with pytest.raises(ConnectorError) as exc:
                client.get_json("/repos/o/r")
        finally:
            client.close()
        assert exc.value.category == category
        assert exc.value.retryable is retryable
        if not retryable:
            assert sleeper.sleeps == []


def test_concurrent_checkpoint_stale_update_rejected(migrated_db: str, tenant_a, tenant_b):
    """True concurrent upserts on file-backed SQLite; stale version must lose."""
    reset_engine()
    init_engine(migrated_db)
    engine = get_engine(migrated_db)

    # Seed data source + initial checkpoint in a setup session.
    setup = Session(engine)
    try:
        uow = UnitOfWork(setup)
        from app.connectors.config import hash_connector_config, validate_connector_config
        from app.domain.enterprise_enums import (
            DataSourceStatus,
            DataSourceType,
            PermissionClassification,
        )

        config = validate_connector_config(
            "github",
            {
                "owner": "octocat",
                "repository": "Hello-World",
                "enabled_streams": ["repository"],
            },
        )
        source = dm.DataSource(
            data_source_id=build_entity_id("ds", tenant_a.tenant_id, "github", "concurrent"),
            tenant_id=tenant_a.tenant_id,
            source_type=DataSourceType.GITHUB,
            display_name="concurrent",
            credential_reference="public://none",
            connector_config=config,
            connector_config_schema_version="1",
            connector_config_hash=hash_connector_config(config),
            status=DataSourceStatus.REGISTERED,
            permission_classification=PermissionClassification.PUBLIC,
        )
        uow.data_sources.add_data_source(tenant_a, source)
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
        # Tenant B independent checkpoint must remain untouched.
        source_b = dm.DataSource(
            data_source_id=build_entity_id("ds", tenant_b.tenant_id, "github", "concurrent-b"),
            tenant_id=tenant_b.tenant_id,
            source_type=DataSourceType.GITHUB,
            display_name="concurrent-b",
            credential_reference="public://none",
            connector_config=config,
            connector_config_schema_version="1",
            connector_config_hash=hash_connector_config(config),
            status=DataSourceStatus.REGISTERED,
            permission_classification=PermissionClassification.PUBLIC,
        )
        uow.data_sources.add_data_source(tenant_b, source_b)
        ckpt_b = dm.ConnectorCheckpoint(
            connector_checkpoint_id=build_entity_id(
                "ckpt", tenant_b.tenant_id, source_b.data_source_id, "repository"
            ),
            tenant_id=tenant_b.tenant_id,
            data_source_id=source_b.data_source_id,
            stream_name="repository",
            cursor_payload={"page": 1},
            cursor_hash=snapshot_hash({"page": 1}),
            version=1,
        )
        uow.connector_checkpoints.upsert(tenant_b, ckpt_b)
        uow.commit()
        data_source_id = source.data_source_id
        data_source_b = source_b.data_source_id
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}
    lock = threading.Lock()

    def worker(name: str, page: int) -> None:
        session = Session(engine)
        try:
            uow = UnitOfWork(session)
            existing = uow.connector_checkpoints.get(
                tenant_a, data_source_id=data_source_id, stream_name="repository"
            )
            assert existing is not None
            barrier.wait(timeout=5)
            updated = existing.model_copy(
                update={
                    "cursor_payload": {"page": page, "worker": name},
                    "cursor_hash": snapshot_hash({"page": page, "worker": name}),
                }
            )
            try:
                uow.connector_checkpoints.upsert(
                    tenant_a, updated, expected_version=existing.version
                )
                uow.commit()
                with lock:
                    results[name] = "ok"
            except EnterpriseConflictError:
                session.rollback()
                with lock:
                    results[name] = "conflict"
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=("w1", 2))
    t2 = threading.Thread(target=worker, args=("w2", 3))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(results.values()) == ["conflict", "ok"]

    # Fresh session inspection
    verify = Session(engine)
    try:
        uow = UnitOfWork(verify)
        final = uow.connector_checkpoints.get(
            tenant_a, data_source_id=data_source_id, stream_name="repository"
        )
        assert final is not None
        assert final.version == 2
        other = uow.connector_checkpoints.get(
            tenant_b, data_source_id=data_source_b, stream_name="repository"
        )
        assert other is not None
        assert other.version == 1
        assert other.cursor_payload == {"page": 1}
    finally:
        verify.close()
        engine.dispose()
        reset_engine()


def test_fetch_failure_leaves_checkpoint_unchanged_fresh_session(
    uow, tenant_a, migrated_db, db_session
):
    from app.connectors.config import hash_connector_config, validate_connector_config
    from app.connectors.errors import ConnectorError
    from app.connectors.fake import FakeGitHubConnector
    from app.connectors.orchestrator import IngestionOrchestrator
    from app.domain.enterprise_enums import (
        DataSourceStatus,
        DataSourceType,
        IngestionRunStatus,
        PermissionClassification,
    )

    config = validate_connector_config(
        "github",
        {
            "owner": "octocat",
            "repository": "Hello-World",
            "enabled_streams": ["repository"],
        },
    )
    source = dm.DataSource(
        data_source_id=build_entity_id("ds", tenant_a.tenant_id, "github", "fail-fetch"),
        tenant_id=tenant_a.tenant_id,
        source_type=DataSourceType.GITHUB,
        display_name="fail-fetch",
        credential_reference="public://none",
        connector_config=config,
        connector_config_schema_version="1",
        connector_config_hash=hash_connector_config(config),
        status=DataSourceStatus.REGISTERED,
        permission_classification=PermissionClassification.PUBLIC,
    )
    uow.data_sources.add_data_source(tenant_a, source)
    uow.commit()

    fake = FakeGitHubConnector(
        fail_with=ConnectorError(
            ConnectorErrorCategory.PROVIDER_UNAVAILABLE, "boom", retryable=False
        )
    )
    result = IngestionOrchestrator(uow, connector=fake).sync_data_source(
        tenant_a, source.data_source_id, streams=["repository"]
    )
    assert result.status == IngestionRunStatus.FAILED
    assert result.counters.fetched == 0

    # Fresh session proves no durable checkpoint/evidence.
    engine = get_engine(migrated_db)
    fresh = Session(engine)
    try:
        fresh_uow = UnitOfWork(fresh)
        assert (
            fresh_uow.connector_checkpoints.get(
                tenant_a, data_source_id=source.data_source_id, stream_name="repository"
            )
            is None
        )
        evidence = fresh_uow.evidence_signals.list_by_source(
            tenant_a, data_source_id=source.data_source_id, limit=10
        )
        assert evidence.total == 0
    finally:
        fresh.close()


def test_normalize_deterministic_across_key_order():
    raw_a = {
        "id": 5,
        "number": 5,
        "title": "T",
        "state": "closed",
        "merged_at": "2024-02-01T00:00:00Z",
        "updated_at": "2024-02-01T00:00:00Z",
        "created_at": "2024-01-01T00:00:00Z",
        "user": {"login": "octocat"},
    }
    raw_b = {
        "user": {"login": "octocat"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-02-01T00:00:00Z",
        "merged_at": "2024-02-01T00:00:00Z",
        "state": "closed",
        "title": "T",
        "number": 5,
        "id": 5,
    }
    e1 = normalize_pull_request(tenant_id="t", data_source_id="d", raw=raw_a)
    e2 = normalize_pull_request(tenant_id="t", data_source_id="d", raw=raw_b)
    assert e1.payload_hash == e2.payload_hash
    assert e1.normalized_event_id == e2.normalized_event_id
    assert e1.payload["state"] == "merged"
