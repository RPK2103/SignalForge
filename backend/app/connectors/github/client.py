"""GitHub REST HTTP client — pagination, rate limits, safe error mapping."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.connectors.errors import ConnectorError, map_http_status_to_error
from app.connectors.protocol import RateLimitState
from app.connectors.retry import Clock, RetryExecutor, RetryPolicy, SystemClock
from app.domain.enterprise_enums import ConnectorErrorCategory

_logger = logging.getLogger("signalforge.connectors.github")

GITHUB_API_HOST = "api.github.com"
GITHUB_API_BASE = f"https://{GITHUB_API_HOST}"
DEFAULT_USER_AGENT = "SignalForge-Connector/0.1 (+https://github.com/signalforge)"
DEFAULT_ACCEPT = "application/vnd.github+json"
DEFAULT_TIMEOUT = 15.0

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')


def parse_link_header(header: str | None) -> dict[str, str]:
    if not header:
        return {}
    links: dict[str, str] = {}
    for match in _LINK_RE.finditer(header):
        links[match.group(2)] = match.group(1)
    return links


def _parse_reset(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, IndexError):
            return None


def extract_rate_limit(headers: httpx.Headers) -> RateLimitState:
    remaining = headers.get("X-RateLimit-Remaining")
    limit = headers.get("X-RateLimit-Limit")
    return RateLimitState(
        limit=int(limit) if limit and limit.isdigit() else None,
        remaining=int(remaining) if remaining and remaining.isdigit() else None,
        reset_at=_parse_reset(headers.get("X-RateLimit-Reset")),
        retry_after_seconds=_parse_retry_after(headers.get("Retry-After")),
        resource=headers.get("X-RateLimit-Resource"),
    )


def is_rate_limit_403(status_code: int, headers: httpx.Headers, body_text: str) -> bool:
    if status_code != 403:
        return False
    remaining = headers.get("X-RateLimit-Remaining")
    if remaining == "0":
        return True
    lowered = body_text.lower()
    return "rate limit" in lowered or "secondary rate limit" in lowered


class GitHubHttpClient:
    """Official GitHub REST client with bounded retries. Tokens never logged."""

    def __init__(
        self,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
        retry_executor: RetryExecutor | None = None,
        clock: Clock | None = None,
        base_url: str = GITHUB_API_BASE,
    ) -> None:
        self._validate_base_url(base_url)
        self._token = token
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._clock = clock or SystemClock()
        self._retry = retry_executor or RetryExecutor(RetryPolicy(), clock=self._clock)
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers=self._headers(),
            follow_redirects=False,
        )
        self.request_count = 0
        self.retry_count = 0
        self.rate_limit_waits = 0
        self.last_rate_limit: RateLimitState | None = None

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.hostname != GITHUB_API_HOST:
            raise ConnectorError(
                ConnectorErrorCategory.INVALID_CONFIGURATION,
                "Only the official GitHub API host is permitted",
                retryable=False,
            )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": DEFAULT_ACCEPT,
            "User-Agent": DEFAULT_USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubHttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, httpx.Headers, dict[str, str]]:
        """GET JSON with bounded retries. Returns (body, headers, link_map)."""
        attempt = 0
        while True:
            attempt += 1
            try:
                self.request_count += 1
                response = self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                error = ConnectorError(
                    ConnectorErrorCategory.TIMEOUT,
                    "GitHub request timed out",
                    retryable=True,
                )
                decision = self._retry.decide(error, attempt)
                if not decision.should_retry:
                    raise error from exc
                self.retry_count += 1
                _logger.info(
                    "connector.retry.attempted connector=github category=timeout "
                    "attempt=%d delay=%.3f",
                    attempt,
                    decision.delay_seconds,
                )
                self._retry.sleep(decision.delay_seconds)
                continue
            except httpx.TransportError as exc:
                error = ConnectorError(
                    ConnectorErrorCategory.TRANSPORT_ERROR,
                    "GitHub transport error",
                    retryable=True,
                )
                decision = self._retry.decide(error, attempt)
                if not decision.should_retry:
                    raise error from exc
                self.retry_count += 1
                _logger.info(
                    "connector.retry.attempted connector=github category=transport "
                    "attempt=%d delay=%.3f",
                    attempt,
                    decision.delay_seconds,
                )
                self._retry.sleep(decision.delay_seconds)
                continue

            rate = extract_rate_limit(response.headers)
            self.last_rate_limit = rate
            body_text = response.text
            rate_limit_403 = is_rate_limit_403(response.status_code, response.headers, body_text)

            if response.status_code >= 400:
                error = map_http_status_to_error(
                    response.status_code,
                    message=f"GitHub API error status={response.status_code}",
                    rate_limit_proven=rate_limit_403,
                )
                decision = self._retry.decide(
                    error,
                    attempt,
                    retry_after_seconds=rate.retry_after_seconds,
                    reset_at=(
                        rate.reset_at
                        if error.category == ConnectorErrorCategory.RATE_LIMITED
                        else None
                    ),
                )
                if decision.should_retry:
                    self.retry_count += 1
                    if error.category == ConnectorErrorCategory.RATE_LIMITED:
                        self.rate_limit_waits += 1
                        _logger.info(
                            "connector.rate_limit.wait connector=github attempt=%d "
                            "delay=%.3f remaining=%s",
                            attempt,
                            decision.delay_seconds,
                            rate.remaining,
                        )
                    else:
                        _logger.info(
                            "connector.retry.attempted connector=github category=%s "
                            "attempt=%d delay=%.3f",
                            error.category.value,
                            attempt,
                            decision.delay_seconds,
                        )
                    self._retry.sleep(decision.delay_seconds)
                    continue
                raise error

            if rate.remaining == 0 and rate.reset_at is not None:
                wait = (rate.reset_at - self._clock.now()).total_seconds()
                if wait > self._retry.policy.max_rate_limit_wait_seconds:
                    raise ConnectorError(
                        ConnectorErrorCategory.RATE_LIMITED,
                        "GitHub rate limit wait exceeds configured maximum",
                        retryable=False,
                    )
                if wait > 0:
                    self.rate_limit_waits += 1
                    _logger.info(
                        "connector.rate_limit.wait connector=github delay=%.3f remaining=0",
                        wait,
                    )
                    self._retry.sleep(wait)

            try:
                body = response.json() if body_text else None
            except json.JSONDecodeError as exc:
                raise ConnectorError(
                    ConnectorErrorCategory.MALFORMED_RESPONSE,
                    "GitHub response was not valid JSON",
                    retryable=False,
                    status_code=response.status_code,
                ) from exc

            links = parse_link_header(response.headers.get("Link"))
            return body, response.headers, links

    @staticmethod
    def page_from_link(url: str) -> int | None:
        query = parse_qs(urlparse(url).query)
        page = query.get("page", [None])[0]
        return int(page) if page and page.isdigit() else None
