"""Connector contract, credentials, config, retry, staged providers."""

from __future__ import annotations

import pytest

from app.connectors.config import reject_secret_keys, validate_connector_config
from app.connectors.credentials import (
    ChainedCredentialResolver,
    EnvironmentCredentialResolver,
    PublicCredentialResolver,
    validate_credential_reference,
)
from app.connectors.errors import ConnectorError, sanitize_error_message
from app.connectors.registry import build_default_registry
from app.connectors.retry import FakeClock, FakeRandom, FakeSleeper, RetryExecutor, RetryPolicy
from app.domain.enterprise_enums import ConnectorErrorCategory


def test_registry_lists_github_operational_and_staged():
    registry = build_default_registry()
    keys = {d.connector_key for d in registry.list_descriptors()}
    assert keys == {"azure_devops", "github", "jira"}
    assert registry.is_operational("github")
    assert not registry.is_operational("jira")
    assert not registry.is_operational("azure_devops")


def test_jira_and_ado_do_not_false_succeed():
    registry = build_default_registry()
    with pytest.raises(ConnectorError) as jira_exc:
        registry.get("jira")
    assert jira_exc.value.category == ConnectorErrorCategory.CONNECTOR_NOT_IMPLEMENTED

    with pytest.raises(ConnectorError) as ado_exc:
        registry.get("azure_devops")
    assert ado_exc.value.category == ConnectorErrorCategory.CONNECTOR_NOT_IMPLEMENTED

    # Even if stub is constructed directly, fetch_page must fail.
    from app.connectors.azure_devops.descriptor import AzureDevOpsStubConnector
    from app.connectors.jira.descriptor import JiraStubConnector
    from app.connectors.protocol import ConnectorContext, ConnectorRequest
    from app.domain.tenant_context import TenantContext

    ctx = ConnectorContext(
        tenant=TenantContext.require("tenant-a"),
        data_source_id="ds_x",
        correlation_id="c1",
    )
    req = ConnectorRequest(stream_name="issues")
    with pytest.raises(ConnectorError) as e1:
        JiraStubConnector().fetch_page(
            ctx, {"base_site": "x.atlassian.net", "project_key": "ABC"}, req
        )
    assert e1.value.category == ConnectorErrorCategory.CONNECTOR_NOT_IMPLEMENTED
    with pytest.raises(ConnectorError) as e2:
        AzureDevOpsStubConnector().fetch_page(ctx, {"organization": "org", "project": "proj"}, req)
    assert e2.value.category == ConnectorErrorCategory.CONNECTOR_NOT_IMPLEMENTED


def test_github_config_validation_and_secret_rejection():
    cfg = validate_connector_config(
        "github",
        {
            "owner": "octocat",
            "repository": "Hello-World",
            "enabled_streams": ["repository", "issues"],
            "page_size": 10,
        },
    )
    assert cfg["owner"] == "octocat"
    with pytest.raises(ConnectorError):
        reject_secret_keys({"token": "x"})
    with pytest.raises(ConnectorError):
        validate_connector_config(
            "github", {"owner": "octocat", "repository": "Hello-World", "api_key": "x"}
        )
    with pytest.raises(ConnectorError):
        validate_connector_config(
            "github", {"owner": "octocat", "repository": "Hello-World", "unknown": 1}
        )


def test_credential_resolvers_and_redaction(monkeypatch):
    public = PublicCredentialResolver().resolve("public://none")
    assert public.token is None
    assert "token" not in repr(public).lower() or "has_token=False" in repr(public)

    with pytest.raises(ConnectorError):
        validate_credential_reference("ghp_abcdefghijklmnopqrstuvwxyz012345")

    with pytest.raises(ConnectorError):
        validate_credential_reference("env://PATH")

    monkeypatch.setenv("SIGNALFORGE_GITHUB_TOKEN", "super-secret-value")
    resolved = EnvironmentCredentialResolver().resolve("env://SIGNALFORGE_GITHUB_TOKEN")
    assert resolved.token == "super-secret-value"
    assert "super-secret-value" not in repr(resolved)
    assert "super-secret-value" not in str(resolved)

    chained = ChainedCredentialResolver()
    assert chained.resolve(None).token is None

    msg = sanitize_error_message("failed auth token=abc123")
    assert "abc123" not in msg
    assert "redacted" in msg.lower()


def test_retry_policy_deterministic_no_real_sleep():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    random_source = FakeRandom([0.0])
    executor = RetryExecutor(
        RetryPolicy(
            max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=10.0, jitter_ratio=0.0
        ),
        clock=clock,
        sleeper=sleeper,
        random_source=random_source,
    )
    err = ConnectorError(ConnectorErrorCategory.TIMEOUT, "timeout", retryable=True)
    d1 = executor.decide(err, 1)
    assert d1.should_retry
    assert d1.delay_seconds == 1.0
    executor.sleep(d1.delay_seconds)
    d2 = executor.decide(err, 2)
    assert d2.delay_seconds == 2.0
    auth = ConnectorError(ConnectorErrorCategory.AUTHENTICATION_ERROR, "nope", retryable=False)
    assert not executor.decide(auth, 1).should_retry
    assert sleeper.sleeps == [1.0]


def test_rate_limit_retry_after_and_max_wait():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    executor = RetryExecutor(
        RetryPolicy(max_attempts=3, max_rate_limit_wait_seconds=5.0, jitter_ratio=0.0),
        clock=clock,
        sleeper=sleeper,
        random_source=FakeRandom([0.0]),
    )
    err = ConnectorError(ConnectorErrorCategory.RATE_LIMITED, "rl", retryable=True)
    ok = executor.decide(err, 1, retry_after_seconds=2.0)
    assert ok.should_retry
    assert ok.delay_seconds == 2.0
    denied = executor.decide(err, 1, retry_after_seconds=30.0)
    assert not denied.should_retry
    assert denied.reason == "rate_limit_wait_exceeds_maximum"
