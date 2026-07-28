"""GitHub client and normalization unit tests (httpx MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.connectors.errors import ConnectorError
from app.connectors.github.client import GitHubHttpClient, parse_link_header
from app.connectors.github.normalize import (
    normalize_issue,
    normalize_pull_request,
    normalize_pull_request_review,
    normalize_release,
    normalize_repository,
)
from app.connectors.retry import FakeClock, FakeRandom, FakeSleeper, RetryExecutor, RetryPolicy
from app.domain.enterprise_enums import ConnectorErrorCategory


def test_parse_link_header():
    links = parse_link_header(
        '<https://api.github.com/x?page=2>; rel="next", '
        '<https://api.github.com/x?page=5>; rel="last"'
    )
    assert "next" in links
    assert "last" in links


def _client(handler, retry=None):
    transport = httpx.MockTransport(handler)
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    executor = retry or RetryExecutor(
        RetryPolicy(max_attempts=3, base_delay_seconds=0.01, jitter_ratio=0.0),
        clock=clock,
        sleeper=sleeper,
        random_source=FakeRandom([0.0]),
    )
    return GitHubHttpClient(transport=transport, retry_executor=executor, clock=clock)


def test_github_headers_and_public_mode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json={"id": 1, "name": "Hello-World"})

    with _client(handler) as client:
        body, headers, _ = client.get_json("/repos/octocat/Hello-World")
    assert body["id"] == 1
    assert seen["headers"]["user-agent"].startswith("SignalForge-Connector")
    assert seen["headers"]["accept"] == "application/vnd.github+json"
    assert "authorization" not in {k.lower() for k in seen["headers"]}


def test_github_auth_header_without_logging_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer secret-token"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = GitHubHttpClient(token="secret-token", transport=transport)
    try:
        client.get_json("/rate_limit")
        assert "secret-token" not in repr(client)
    finally:
        client.close()


def test_github_status_classification():
    cases = [
        (401, ConnectorErrorCategory.AUTHENTICATION_ERROR, False),
        (403, ConnectorErrorCategory.PERMISSION_DENIED, False),
        (404, ConnectorErrorCategory.REPOSITORY_NOT_FOUND, False),
        (429, ConnectorErrorCategory.RATE_LIMITED, True),
        (500, ConnectorErrorCategory.PROVIDER_UNAVAILABLE, True),
    ]
    for status, category, _retryable in cases:

        def handler(request: httpx.Request, status=status) -> httpx.Response:
            return httpx.Response(status, json={"message": "err"})

        clock = FakeClock()
        sleeper = FakeSleeper(clock)
        executor = RetryExecutor(
            RetryPolicy(max_attempts=1, jitter_ratio=0.0),
            clock=clock,
            sleeper=sleeper,
            random_source=FakeRandom([0.0]),
        )
        with pytest.raises(ConnectorError) as exc:
            with _client(handler, retry=executor) as client:
                client.get_json("/repos/x/y")
        assert exc.value.category == category


def test_github_rate_limit_403_and_retry_after():
    calls = {"n": 0}
    clock = FakeClock()
    reset_ts = int(clock.now().timestamp()) + 2

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                403,
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                    "Retry-After": "1",
                },
                json={"message": "API rate limit exceeded"},
            )
        return httpx.Response(200, json={"id": 1})

    sleeper = FakeSleeper(clock)
    executor = RetryExecutor(
        RetryPolicy(max_attempts=3, max_rate_limit_wait_seconds=60, jitter_ratio=0.0),
        clock=clock,
        sleeper=sleeper,
        random_source=FakeRandom([0.0]),
    )
    transport = httpx.MockTransport(handler)
    client = GitHubHttpClient(transport=transport, retry_executor=executor, clock=clock)
    try:
        body, _, _ = client.get_json("/repos/o/r")
    finally:
        client.close()
    assert body["id"] == 1
    assert client.retry_count >= 1
    assert sleeper.sleeps


def test_github_malformed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json", headers={"content-type": "application/json"})

    with pytest.raises(ConnectorError) as exc:
        with _client(handler) as client:
            client.get_json("/repos/o/r")
    assert exc.value.category == ConnectorErrorCategory.MALFORMED_RESPONSE


def test_arbitrary_base_url_rejected():
    with pytest.raises(ConnectorError) as exc:
        GitHubHttpClient(base_url="https://evil.example.com")
    assert exc.value.category == ConnectorErrorCategory.INVALID_CONFIGURATION


def test_normalization_snapshots_stable_and_no_email():
    raw_repo = {
        "id": 1296269,
        "name": "Hello-World",
        "full_name": "octocat/Hello-World",
        "private": False,
        "visibility": "public",
        "default_branch": "master",
        "archived": False,
        "updated_at": "2024-01-01T00:00:00Z",
        "created_at": "2011-01-26T19:01:12Z",
        "owner": {"login": "octocat", "email": "octocat@example.com"},
        "html_url": "https://github.com/octocat/Hello-World",
    }
    e1 = normalize_repository(tenant_id="t1", data_source_id="ds1", raw=raw_repo)
    e2 = normalize_repository(tenant_id="t1", data_source_id="ds1", raw=raw_repo)
    assert e1.normalized_event_id == e2.normalized_event_id
    assert e1.payload_hash == e2.payload_hash
    assert e1.event_type == "github.repository.snapshot"
    assert "email" not in json.dumps(e1.payload)

    pr = normalize_pull_request(
        tenant_id="t1",
        data_source_id="ds1",
        raw={
            "id": 1,
            "number": 1347,
            "title": "PR",
            "state": "open",
            "draft": False,
            "user": {"login": "octocat", "email": "x@y.com"},
            "updated_at": "2024-02-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "html_url": "https://github.com/o/r/pull/1347",
        },
    )
    assert pr.event_type == "github.pull_request.snapshot"
    assert "email" not in json.dumps(pr.payload)

    review = normalize_pull_request_review(
        tenant_id="t1",
        data_source_id="ds1",
        raw={
            "id": 80,
            "state": "APPROVED",
            "user": {"login": "reviewer"},
            "submitted_at": "2024-02-02T00:00:00Z",
            "body": "looks good",
        },
        pull_request_id="1",
    )
    assert review.event_type == "github.pull_request_review.snapshot"
    assert "looks good" not in json.dumps(review.payload)

    with pytest.raises(ConnectorError):
        normalize_issue(
            tenant_id="t1",
            data_source_id="ds1",
            raw={
                "id": 1,
                "number": 1,
                "title": "x",
                "pull_request": {},
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    issue = normalize_issue(
        tenant_id="t1",
        data_source_id="ds1",
        raw={
            "id": 2,
            "number": 2,
            "title": "Bug",
            "state": "open",
            "updated_at": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "labels": [{"name": "bug"}],
            "user": {"login": "octocat"},
        },
    )
    assert issue.event_type == "github.issue.snapshot"

    release = normalize_release(
        tenant_id="t1",
        data_source_id="ds1",
        raw={
            "id": 3,
            "tag_name": "v1.0.0",
            "name": "v1.0.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2024-03-01T00:00:00Z",
            "created_at": "2024-03-01T00:00:00Z",
            "author": {"login": "octocat"},
        },
    )
    assert release.payload["not_a_deployment"] is True
