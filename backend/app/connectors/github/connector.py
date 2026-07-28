"""Complete GitHub connector — streams, pagination, normalization."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from app.connectors.config import GitHubConnectorConfig, validate_connector_config
from app.connectors.errors import ConnectorError
from app.connectors.github.client import GitHubHttpClient
from app.connectors.github.normalize import NORMALIZERS
from app.connectors.protocol import (
    ConnectorCapabilities,
    ConnectorCheckpointCursor,
    ConnectorContext,
    ConnectorDescriptor,
    ConnectorPage,
    ConnectorRequest,
    ConnectorStream,
    NormalizedConnectorEvent,
)
from app.connectors.retry import Clock, RetryExecutor, SystemClock
from app.domain.enterprise_enums import ConnectorErrorCategory, DataSourceType

_logger = logging.getLogger("signalforge.connectors.github")

GITHUB_STREAMS = [
    ConnectorStream(name="repository", display_name="Repository", supports_incremental=False),
    ConnectorStream(name="pull_requests", display_name="Pull Requests"),
    ConnectorStream(name="pull_request_reviews", display_name="Pull Request Reviews"),
    ConnectorStream(name="issues", display_name="Issues"),
    ConnectorStream(name="releases", display_name="Releases"),
]


def _empty_checkpoint() -> ConnectorCheckpointCursor:
    return ConnectorCheckpointCursor(payload={"page": 1, "since": None, "high_watermark": None})


class GitHubConnector:
    """Operational GitHub REST connector (polling only; no webhooks/OAuth)."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        retry_executor: RetryExecutor | None = None,
        clock: Clock | None = None,
        client_factory: Callable[..., GitHubHttpClient] | None = None,
    ) -> None:
        self._transport = transport
        self._retry = retry_executor
        self._clock = clock or SystemClock()
        self._client_factory = client_factory or GitHubHttpClient

    def descriptor(self) -> ConnectorDescriptor:
        return ConnectorDescriptor(
            connector_key="github",
            display_name="GitHub",
            source_type=DataSourceType.GITHUB,
            streams=list(GITHUB_STREAMS),
            capabilities=ConnectorCapabilities(
                supports_initial_sync=True,
                supports_incremental_sync=True,
                supports_unauthenticated=True,
                requires_credential_reference=False,
                supports_webhooks=False,
                operational=True,
            ),
            documentation_notes=(
                "Official GitHub REST API polling. Public unauthenticated access supported. "
                "Webhooks and OAuth are not implemented."
            ),
        )

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return validate_connector_config("github", config)

    def list_streams(self, config: dict[str, Any]) -> list[ConnectorStream]:
        validated = GitHubConnectorConfig.model_validate(self.validate_config(config))
        by_name = {s.name: s for s in GITHUB_STREAMS}
        return [by_name[name] for name in validated.enabled_streams if name in by_name]

    def fetch_page(
        self,
        context: ConnectorContext,
        config: dict[str, Any],
        request: ConnectorRequest,
    ) -> ConnectorPage:
        validated = GitHubConnectorConfig.model_validate(self.validate_config(config))
        if request.stream_name not in validated.enabled_streams:
            raise ConnectorError(
                ConnectorErrorCategory.INVALID_CONFIGURATION,
                f"Stream '{request.stream_name}' is not enabled",
                retryable=False,
            )
        page_size = min(request.page_size, validated.page_size)
        overlap = request.overlap_seconds if request.overlap_seconds else validated.overlap_seconds
        max_pages = context.max_pages or request.maximum_pages or validated.maximum_pages

        client = self._client_factory(
            token=context.credential_token,
            transport=self._transport,
            retry_executor=self._retry,
            clock=self._clock,
        )
        try:
            if request.stream_name == "repository":
                return self._fetch_repository(client, context, validated, request)
            if request.stream_name == "pull_requests":
                return self._fetch_pull_requests(
                    client, context, validated, request, page_size, overlap, max_pages
                )
            if request.stream_name == "pull_request_reviews":
                return self._fetch_reviews(
                    client, context, validated, request, page_size, overlap, max_pages
                )
            if request.stream_name == "issues":
                return self._fetch_issues(
                    client, context, validated, request, page_size, overlap, max_pages
                )
            if request.stream_name == "releases":
                return self._fetch_releases(
                    client, context, validated, request, page_size, max_pages
                )
            raise ConnectorError(
                ConnectorErrorCategory.INVALID_CONFIGURATION,
                f"Unknown stream: {request.stream_name}",
                retryable=False,
            )
        finally:
            client.close()

    def _owner_repo(self, config: GitHubConnectorConfig) -> str:
        return f"{config.owner}/{config.repository}"

    def _normalize_many(
        self,
        stream: str,
        records: list[dict[str, Any]],
        context: ConnectorContext,
        *,
        extra: dict[str, Any] | None = None,
    ) -> list[NormalizedConnectorEvent]:
        normalizer = NORMALIZERS[stream]
        events: list[NormalizedConnectorEvent] = []
        for raw in records:
            kwargs = {
                "tenant_id": context.tenant.tenant_id,
                "data_source_id": context.data_source_id,
                "raw": raw,
            }
            if extra:
                kwargs.update(extra)
            events.append(normalizer(**kwargs))
        events.sort(key=lambda e: (e.event_time, e.source_record_id))
        return events

    def _fetch_repository(
        self,
        client: GitHubHttpClient,
        context: ConnectorContext,
        config: GitHubConnectorConfig,
        request: ConnectorRequest,
    ) -> ConnectorPage:
        path = f"/repos/{self._owner_repo(config)}"
        body, headers, _links = client.get_json(path)
        if not isinstance(body, dict):
            raise ConnectorError(
                ConnectorErrorCategory.MALFORMED_RESPONSE,
                "Expected repository object",
                retryable=False,
            )
        events = self._normalize_many("repository", [body], context)
        _logger.info(
            "connector.page.fetched connector=github stream=repository tenant_id=%s "
            "data_source_id=%s records=1 correlation_id=%s",
            context.tenant.tenant_id,
            context.data_source_id,
            context.correlation_id,
        )
        return ConnectorPage(
            stream_name="repository",
            records=[body],
            normalized_events=events,
            next_checkpoint=ConnectorCheckpointCursor(
                payload={"page": 1, "completed": True},
                high_watermark_time=events[0].event_time if events else None,
                high_watermark_source_id=events[0].source_record_id if events else None,
                etag=headers.get("ETag"),
            ),
            rate_limit=client.last_rate_limit,
            has_more=False,
            request_count=client.request_count,
            etag=headers.get("ETag"),
        )

    def _checkpoint_page(self, checkpoint: ConnectorCheckpointCursor | None) -> int:
        if checkpoint is None:
            return 1
        page = checkpoint.payload.get("page", 1)
        return int(page) if page else 1

    def _since_filter(
        self,
        checkpoint: ConnectorCheckpointCursor | None,
        overlap_seconds: int,
    ) -> datetime | None:
        if checkpoint is None or checkpoint.high_watermark_time is None:
            return None
        hw = checkpoint.high_watermark_time
        if hw.tzinfo is None:
            hw = hw.replace(tzinfo=timezone.utc)
        return hw - timedelta(seconds=overlap_seconds)

    def _fetch_pull_requests(
        self,
        client: GitHubHttpClient,
        context: ConnectorContext,
        config: GitHubConnectorConfig,
        request: ConnectorRequest,
        page_size: int,
        overlap: int,
        max_pages: int | None,
    ) -> ConnectorPage:
        page = self._checkpoint_page(request.checkpoint)
        if max_pages is not None and page > max_pages:
            return ConnectorPage(
                stream_name="pull_requests",
                has_more=False,
                request_count=0,
                next_checkpoint=request.checkpoint or _empty_checkpoint(),
            )
        path = f"/repos/{self._owner_repo(config)}/pulls"
        body, headers, links = client.get_json(
            path,
            params={
                "state": "all",
                "sort": "updated",
                "direction": "asc",
                "per_page": page_size,
                "page": page,
            },
        )
        if not isinstance(body, list):
            raise ConnectorError(
                ConnectorErrorCategory.MALFORMED_RESPONSE,
                "Expected pull request list",
                retryable=False,
            )
        since = self._since_filter(request.checkpoint, overlap)
        filtered = []
        for item in body:
            updated = item.get("updated_at")
            if since and updated:
                from app.connectors.github.normalize import parse_github_datetime

                ts = parse_github_datetime(updated)
                if ts and ts < since:
                    continue
            filtered.append(item)
        events = self._normalize_many("pull_requests", filtered, context)
        has_more = "next" in links
        if max_pages is not None and page >= max_pages:
            has_more = False
        next_page = page + 1 if has_more else page
        hw_time = (
            events[-1].event_time
            if events
            else (request.checkpoint.high_watermark_time if request.checkpoint else None)
        )
        hw_id = (
            events[-1].source_record_id
            if events
            else (request.checkpoint.high_watermark_source_id if request.checkpoint else None)
        )
        _logger.info(
            "connector.page.fetched connector=github stream=pull_requests tenant_id=%s "
            "data_source_id=%s page=%d records=%d correlation_id=%s",
            context.tenant.tenant_id,
            context.data_source_id,
            page,
            len(filtered),
            context.correlation_id,
        )
        return ConnectorPage(
            stream_name="pull_requests",
            records=filtered,
            normalized_events=events,
            next_checkpoint=ConnectorCheckpointCursor(
                payload={"page": next_page if has_more else page, "completed": not has_more},
                high_watermark_time=hw_time,
                high_watermark_source_id=hw_id,
                etag=headers.get("ETag"),
            ),
            rate_limit=client.last_rate_limit,
            has_more=has_more,
            request_count=client.request_count,
            etag=headers.get("ETag"),
        )

    def _fetch_issues(
        self,
        client: GitHubHttpClient,
        context: ConnectorContext,
        config: GitHubConnectorConfig,
        request: ConnectorRequest,
        page_size: int,
        overlap: int,
        max_pages: int | None,
    ) -> ConnectorPage:
        page = self._checkpoint_page(request.checkpoint)
        if max_pages is not None and page > max_pages:
            return ConnectorPage(
                stream_name="issues",
                has_more=False,
                request_count=0,
                next_checkpoint=request.checkpoint or _empty_checkpoint(),
            )
        path = f"/repos/{self._owner_repo(config)}/issues"
        body, headers, links = client.get_json(
            path,
            params={
                "state": "all",
                "sort": "updated",
                "direction": "asc",
                "per_page": page_size,
                "page": page,
            },
        )
        if not isinstance(body, list):
            raise ConnectorError(
                ConnectorErrorCategory.MALFORMED_RESPONSE,
                "Expected issue list",
                retryable=False,
            )
        # Exclude pull requests returned by the issues endpoint.
        issues = [
            item for item in body if isinstance(item, dict) and item.get("pull_request") is None
        ]
        since = self._since_filter(request.checkpoint, overlap)
        filtered = []
        for item in issues:
            updated = item.get("updated_at")
            if since and updated:
                from app.connectors.github.normalize import parse_github_datetime

                ts = parse_github_datetime(updated)
                if ts and ts < since:
                    continue
            filtered.append(item)
        events = self._normalize_many("issues", filtered, context)
        has_more = "next" in links
        if max_pages is not None and page >= max_pages:
            has_more = False
        next_page = page + 1 if has_more else page
        hw_time = (
            events[-1].event_time
            if events
            else (request.checkpoint.high_watermark_time if request.checkpoint else None)
        )
        hw_id = (
            events[-1].source_record_id
            if events
            else (request.checkpoint.high_watermark_source_id if request.checkpoint else None)
        )
        return ConnectorPage(
            stream_name="issues",
            records=filtered,
            normalized_events=events,
            next_checkpoint=ConnectorCheckpointCursor(
                payload={"page": next_page if has_more else page, "completed": not has_more},
                high_watermark_time=hw_time,
                high_watermark_source_id=hw_id,
                etag=headers.get("ETag"),
            ),
            rate_limit=client.last_rate_limit,
            has_more=has_more,
            request_count=client.request_count,
            etag=headers.get("ETag"),
        )

    def _fetch_releases(
        self,
        client: GitHubHttpClient,
        context: ConnectorContext,
        config: GitHubConnectorConfig,
        request: ConnectorRequest,
        page_size: int,
        max_pages: int | None,
    ) -> ConnectorPage:
        page = self._checkpoint_page(request.checkpoint)
        if max_pages is not None and page > max_pages:
            return ConnectorPage(
                stream_name="releases",
                has_more=False,
                request_count=0,
                next_checkpoint=request.checkpoint or _empty_checkpoint(),
            )
        path = f"/repos/{self._owner_repo(config)}/releases"
        body, headers, links = client.get_json(path, params={"per_page": page_size, "page": page})
        if not isinstance(body, list):
            raise ConnectorError(
                ConnectorErrorCategory.MALFORMED_RESPONSE,
                "Expected release list",
                retryable=False,
            )
        events = self._normalize_many("releases", body, context)
        has_more = "next" in links
        if max_pages is not None and page >= max_pages:
            has_more = False
        next_page = page + 1 if has_more else page
        hw_time = (
            events[-1].event_time
            if events
            else (request.checkpoint.high_watermark_time if request.checkpoint else None)
        )
        hw_id = (
            events[-1].source_record_id
            if events
            else (request.checkpoint.high_watermark_source_id if request.checkpoint else None)
        )
        return ConnectorPage(
            stream_name="releases",
            records=body,
            normalized_events=events,
            next_checkpoint=ConnectorCheckpointCursor(
                payload={"page": next_page if has_more else page, "completed": not has_more},
                high_watermark_time=hw_time,
                high_watermark_source_id=hw_id,
                etag=headers.get("ETag"),
            ),
            rate_limit=client.last_rate_limit,
            has_more=has_more,
            request_count=client.request_count,
            etag=headers.get("ETag"),
        )

    def _fetch_reviews(
        self,
        client: GitHubHttpClient,
        context: ConnectorContext,
        config: GitHubConnectorConfig,
        request: ConnectorRequest,
        page_size: int,
        overlap: int,
        max_pages: int | None,
    ) -> ConnectorPage:
        """Fetch reviews for recently updated PRs (bounded).

        GitHub has no global review list endpoint; reviews are fetched per PR.
        Cursor payload tracks ``pr_page`` and optional ``pr_number``.
        """
        cursor = request.checkpoint.payload if request.checkpoint else {}
        pr_page = int(cursor.get("pr_page") or cursor.get("page") or 1)
        if max_pages is not None and pr_page > max_pages:
            return ConnectorPage(
                stream_name="pull_request_reviews",
                has_more=False,
                request_count=0,
                next_checkpoint=request.checkpoint or _empty_checkpoint(),
            )

        pulls_path = f"/repos/{self._owner_repo(config)}/pulls"
        pulls_body, _headers, pull_links = client.get_json(
            pulls_path,
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": min(page_size, 10),
                "page": pr_page,
            },
        )
        if not isinstance(pulls_body, list):
            raise ConnectorError(
                ConnectorErrorCategory.MALFORMED_RESPONSE,
                "Expected pull request list for reviews",
                retryable=False,
            )

        all_reviews: list[dict[str, Any]] = []
        events: list[NormalizedConnectorEvent] = []
        for pr in pulls_body[: min(page_size, 10)]:
            number = pr.get("number")
            pr_id = str(pr.get("id"))
            if number is None:
                continue
            reviews_path = f"/repos/{self._owner_repo(config)}/pulls/{number}/reviews"
            reviews_body, _, _ = client.get_json(
                reviews_path, params={"per_page": page_size, "page": 1}
            )
            if not isinstance(reviews_body, list):
                continue
            for review in reviews_body:
                if isinstance(review, dict):
                    all_reviews.append(review)
                    events.append(
                        NORMALIZERS["pull_request_reviews"](
                            tenant_id=context.tenant.tenant_id,
                            data_source_id=context.data_source_id,
                            raw=review,
                            pull_request_id=pr_id,
                        )
                    )
        events.sort(key=lambda e: (e.event_time, e.source_record_id))
        has_more = "next" in pull_links
        if max_pages is not None and pr_page >= max_pages:
            has_more = False
        next_pr_page = pr_page + 1 if has_more else pr_page
        hw_time = (
            events[-1].event_time
            if events
            else (request.checkpoint.high_watermark_time if request.checkpoint else None)
        )
        hw_id = (
            events[-1].source_record_id
            if events
            else (request.checkpoint.high_watermark_source_id if request.checkpoint else None)
        )
        return ConnectorPage(
            stream_name="pull_request_reviews",
            records=all_reviews,
            normalized_events=events,
            next_checkpoint=ConnectorCheckpointCursor(
                payload={
                    "page": next_pr_page if has_more else pr_page,
                    "pr_page": next_pr_page if has_more else pr_page,
                    "completed": not has_more,
                },
                high_watermark_time=hw_time,
                high_watermark_source_id=hw_id,
            ),
            rate_limit=client.last_rate_limit,
            has_more=has_more,
            request_count=client.request_count,
        )
