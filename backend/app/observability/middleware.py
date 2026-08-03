"""HTTP request telemetry middleware (Phase 3 Prompt 8).

Placed OUTERMOST so it observes every response — including the 401 returned by
the authentication middleware and 403/422 produced by exception handlers — and
so it owns correlation-ID sanitization and trace-context propagation for the
whole request.

Critical status semantics (see architecture doc):
- 2xx/3xx -> success (normal request);
- 400/404/409/422 -> client/domain outcome (NOT server failure);
- 401 -> authentication denial (NOT server failure);
- 403 -> authorization denial (NOT server failure);
- 429 -> rate-limit outcome;
- 5xx / unhandled exception -> server/application failure.

Only normalized route templates are used as labels (never raw paths with IDs),
and only allowlisted low-cardinality attributes are recorded.
"""

from __future__ import annotations

import asyncio
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.correlation import (
    CORRELATION_HEADER,
    TRACEPARENT_HEADER,
    parse_traceparent,
    sanitize_correlation_id,
)
from app.core.logging_context import bind_correlation_id, bind_trace_context, clear_context
from app.observability.attributes import bounded_status_code, status_family
from app.observability.metrics import MetricName, OperationOutcome
from app.observability.runtime import get_observability_provider

_logger = logging.getLogger("signalforge.http")

_DB_TIMEOUT_MARKERS = ("statement timeout", "querycanceled", "operationaltimeout")


def normalize_route(request: Request, status_code: int) -> str:
    """Return a normalized route template, never a raw path with IDs."""
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None) or getattr(route, "path", None)
    if path_format:
        return str(path_format)
    if status_code == 404:
        return "__not_found__"
    return "__unmatched__"


def classify_outcome(status_code: int) -> OperationOutcome:
    if status_code == 401:
        return OperationOutcome.AUTHENTICATION_DENIED
    if status_code == 403:
        return OperationOutcome.AUTHORIZATION_DENIED
    if status_code == 429:
        return OperationOutcome.RATE_LIMITED
    if 500 <= status_code < 600:
        return OperationOutcome.SERVER_ERROR
    if 400 <= status_code < 500:
        return OperationOutcome.CLIENT_ERROR
    return OperationOutcome.SUCCESS


class RequestTelemetryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        provider = get_observability_provider()

        correlation_id = sanitize_correlation_id(request.headers.get(CORRELATION_HEADER))
        request.state.correlation_id = correlation_id
        bind_correlation_id(correlation_id)

        traceparent = parse_traceparent(request.headers.get(TRACEPARENT_HEADER))
        if traceparent is not None:
            bind_trace_context(trace_id=traceparent[0], span_id=traceparent[1])

        method = request.method
        start = time.perf_counter()
        self._safe(lambda: provider.set_gauge(MetricName.HTTP_ACTIVE_REQUESTS, 1.0))

        status_code = 500
        outcome = OperationOutcome.SERVER_ERROR
        unhandled = False
        cancelled = False
        try:
            response = await call_next(request)
            status_code = response.status_code
            outcome = classify_outcome(status_code)
        except asyncio.CancelledError:
            cancelled = True
            outcome = OperationOutcome.CANCELLED
            raise
        except Exception as exc:  # noqa: BLE001 - record then re-raise for ServerError handler
            unhandled = True
            status_code = 500
            outcome = OperationOutcome.SERVER_ERROR
            self._record_db_timeout(request, exc)
            _logger.exception(
                "http.request.unhandled method=%s route=%s",
                method,
                normalize_route(request, status_code),
            )
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            route = normalize_route(request, status_code)
            self._emit(
                provider,
                method=method,
                route=route,
                status_code=status_code,
                outcome=outcome,
                elapsed_ms=elapsed_ms,
                unhandled=unhandled,
                cancelled=cancelled,
            )
            clear_context()

        response.headers.setdefault(CORRELATION_HEADER, correlation_id)
        return response

    def _emit(
        self,
        provider,
        *,
        method: str,
        route: str,
        status_code: int,
        outcome: OperationOutcome,
        elapsed_ms: float,
        unhandled: bool,
        cancelled: bool,
    ) -> None:
        family = status_family(status_code)
        attributes = {
            "http_method": method,
            "route": route,
            "status_family": family,
            "status_code": bounded_status_code(status_code),
            "outcome": outcome.value,
        }
        # Metric recording must never change response behavior.
        self._safe(lambda: provider.increment(MetricName.HTTP_REQUESTS, attributes=attributes))
        self._safe(
            lambda: provider.record_value(
                MetricName.HTTP_REQUEST_DURATION, elapsed_ms, attributes=attributes
            )
        )
        self._safe(lambda: provider.set_gauge(MetricName.HTTP_ACTIVE_REQUESTS, 0.0))

        if cancelled:
            self._safe(
                lambda: provider.increment(MetricName.HTTP_CANCELLATIONS, attributes=attributes)
            )
            return

        if outcome is OperationOutcome.AUTHENTICATION_DENIED:
            self._safe(
                lambda: provider.increment(
                    MetricName.HTTP_AUTHENTICATION_DENIALS, attributes=attributes
                )
            )
        elif outcome is OperationOutcome.AUTHORIZATION_DENIED:
            self._safe(
                lambda: provider.increment(
                    MetricName.HTTP_AUTHORIZATION_DENIALS, attributes=attributes
                )
            )
        elif outcome is OperationOutcome.RATE_LIMITED:
            self._safe(
                lambda: provider.increment(MetricName.HTTP_RATE_LIMITS, attributes=attributes)
            )
        elif outcome is OperationOutcome.SERVER_ERROR:
            # ONLY genuine server failures increment the server-error metric.
            self._safe(
                lambda: provider.increment(MetricName.HTTP_SERVER_ERRORS, attributes=attributes)
            )
            if unhandled:
                self._safe(
                    lambda: provider.increment(
                        MetricName.HTTP_UNHANDLED_EXCEPTIONS, attributes=attributes
                    )
                )

    def _record_db_timeout(self, request: Request, exc: Exception) -> None:
        text = f"{type(exc).__name__}:{exc}".lower()
        if any(marker in text for marker in _DB_TIMEOUT_MARKERS):
            provider = get_observability_provider()
            self._safe(lambda: provider.increment(MetricName.HTTP_DB_TIMEOUTS))

    @staticmethod
    def _safe(action) -> None:
        try:
            action()
        except Exception:  # noqa: BLE001 - telemetry must never break the request
            _logger.debug("telemetry emit failed", exc_info=True)


__all__ = ["RequestTelemetryMiddleware", "normalize_route", "classify_outcome"]
