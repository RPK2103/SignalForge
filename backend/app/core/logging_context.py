"""Context-local diagnostic identifiers for structured logging (Prompt 8).

A ``ContextVar`` carries the correlation ID and trace/span IDs for the current
request or operation so structured log records can include them without threading
them through every function signature. Values are safe diagnostic identifiers
only — never tokens, claims, tenant IDs or principal IDs.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

_correlation_id: ContextVar[str | None] = ContextVar("sf_correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("sf_trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("sf_span_id", default=None)


@dataclass(frozen=True, slots=True)
class LogContextSnapshot:
    correlation_id: str | None
    trace_id: str | None
    span_id: str | None


def bind_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def bind_trace_context(*, trace_id: str | None, span_id: str | None) -> None:
    _trace_id.set(trace_id)
    _span_id.set(span_id)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def current_snapshot() -> LogContextSnapshot:
    return LogContextSnapshot(
        correlation_id=_correlation_id.get(),
        trace_id=_trace_id.get(),
        span_id=_span_id.get(),
    )


def clear_context() -> None:
    _correlation_id.set(None)
    _trace_id.set(None)
    _span_id.set(None)
