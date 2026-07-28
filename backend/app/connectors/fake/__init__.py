"""Deterministic fake connectors for failure and retry testing."""

from __future__ import annotations

from typing import Any, Callable

from app.connectors.errors import ConnectorError
from app.connectors.github.normalize import normalize_repository
from app.connectors.protocol import (
    ConnectorCapabilities,
    ConnectorCheckpointCursor,
    ConnectorContext,
    ConnectorDescriptor,
    ConnectorPage,
    ConnectorRequest,
    ConnectorStream,
)
from app.domain.enterprise_enums import DataSourceType


class FakeGitHubConnector:
    """In-memory GitHub-shaped connector with scripted pages/failures."""

    def __init__(
        self,
        *,
        pages: dict[str, list[ConnectorPage]] | None = None,
        fail_with: ConnectorError | None = None,
        fail_on_attempt: dict[str, list[ConnectorError | None]] | None = None,
    ) -> None:
        self._pages = pages or {}
        self._cursors: dict[str, int] = {}
        self._fail_with = fail_with
        self._fail_on_attempt = fail_on_attempt or {}
        self._attempts: dict[str, int] = {}
        self.fetch_calls = 0

    def descriptor(self) -> ConnectorDescriptor:
        return ConnectorDescriptor(
            connector_key="fake_github",
            display_name="Fake GitHub",
            source_type=DataSourceType.GITHUB,
            streams=[
                ConnectorStream(name="repository", display_name="Repository"),
                ConnectorStream(name="pull_requests", display_name="Pull Requests"),
                ConnectorStream(name="issues", display_name="Issues"),
                ConnectorStream(name="releases", display_name="Releases"),
                ConnectorStream(name="pull_request_reviews", display_name="Reviews"),
            ],
            capabilities=ConnectorCapabilities(supports_unauthenticated=True, operational=True),
        )

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        from app.connectors.config import validate_connector_config

        return validate_connector_config("github", config)

    def list_streams(self, config: dict[str, Any]) -> list[ConnectorStream]:
        self.validate_config(config)
        return list(self.descriptor().streams)

    def fetch_page(
        self,
        context: ConnectorContext,
        config: dict[str, Any],
        request: ConnectorRequest,
    ) -> ConnectorPage:
        self.fetch_calls += 1
        stream = request.stream_name
        self._attempts[stream] = self._attempts.get(stream, 0) + 1
        attempt = self._attempts[stream]

        scripted = self._fail_on_attempt.get(stream)
        if scripted and attempt <= len(scripted):
            err = scripted[attempt - 1]
            if err is not None:
                raise err
        if self._fail_with is not None:
            raise self._fail_with

        pages = self._pages.get(stream, [])
        idx = self._cursors.get(stream, 0)
        if idx >= len(pages):
            return ConnectorPage(
                stream_name=stream,
                records=[],
                normalized_events=[],
                next_checkpoint=request.checkpoint
                or ConnectorCheckpointCursor(payload={"page": 1, "completed": True}),
                has_more=False,
                request_count=1,
            )
        page = pages[idx]
        self._cursors[stream] = idx + 1
        return page


def make_repo_page(
    context: ConnectorContext,
    *,
    repo_id: int = 1,
    full_name: str = "octocat/Hello-World",
    updated_at: str = "2026-01-01T00:00:00Z",
) -> ConnectorPage:
    owner, name = full_name.split("/", 1)
    raw = {
        "id": repo_id,
        "name": name,
        "full_name": full_name,
        "private": False,
        "visibility": "public",
        "default_branch": "master",
        "archived": False,
        "updated_at": updated_at,
        "created_at": "2011-01-26T19:01:12Z",
        "owner": {"login": owner},
        "html_url": f"https://github.com/{full_name}",
        "node_id": "R_fake",
    }
    event = normalize_repository(
        tenant_id=context.tenant.tenant_id,
        data_source_id=context.data_source_id,
        raw=raw,
    )
    return ConnectorPage(
        stream_name="repository",
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


class FlakyTransportFactory:
    """Helper to build scripted httpx MockTransport handlers."""

    def __init__(self, handler: Callable):
        import httpx

        self.transport = httpx.MockTransport(handler)
