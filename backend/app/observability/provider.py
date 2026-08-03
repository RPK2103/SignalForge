"""Observability provider protocol and deterministic implementations (Prompt 8).

Domain code records telemetry through :class:`ObservabilityProvider` only. Two
built-in providers cover tests and local development:

- :class:`NoOpObservabilityProvider` — records nothing (safe default).
- :class:`InMemoryObservabilityProvider` — deterministic capture for tests.

Both are pure Python with no network calls. The OpenTelemetry provider lives in
``app.observability.otel`` and is only constructed at the application edge.

Design guarantees:
- recording telemetry NEVER raises into the caller (fail-open for ordinary
  metrics/traces); a provider failure is swallowed and counted, never propagated;
- attributes are always run through the :class:`TelemetryAttributePolicy` before
  being stored/exported, so cardinality and privacy are enforced centrally.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.observability.attributes import TelemetryAttributePolicy
from app.observability.metrics import MetricName, SpanStatus

_logger = logging.getLogger("signalforge.observability")


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Minimal, exporter-independent trace context."""

    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    sampled: bool = True


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Describes an instrumented operation (span)."""

    operation: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetricPoint:
    name: str
    value: float
    attributes: dict[str, str]
    kind: str  # "counter" | "gauge" | "histogram"


class ObservabilityProvider(Protocol):
    def increment(
        self, metric: MetricName, *, value: float = 1.0, attributes: dict[str, Any] | None = None
    ) -> None: ...

    def record_value(
        self, metric: MetricName, value: float, *, attributes: dict[str, Any] | None = None
    ) -> None: ...

    def set_gauge(
        self, metric: MetricName, value: float, *, attributes: dict[str, Any] | None = None
    ) -> None: ...

    def start_span(
        self, operation: str, *, attributes: dict[str, Any] | None = None
    ) -> "SpanHandle": ...

    def shutdown(self) -> None: ...


class SpanHandle(Protocol):
    def set_status(self, status: SpanStatus) -> None: ...
    def set_attribute(self, key: str, value: Any) -> None: ...
    def end(self) -> None: ...


# ---------------------------------------------------------------------------
# No-op provider
# ---------------------------------------------------------------------------
class _NoOpSpan:
    def set_status(self, status: SpanStatus) -> None:  # noqa: D401 - no-op
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def end(self) -> None:
        return None


class NoOpObservabilityProvider:
    """Records nothing. Safe default when observability is disabled."""

    def increment(self, metric, *, value=1.0, attributes=None) -> None:
        return None

    def record_value(self, metric, value, *, attributes=None) -> None:
        return None

    def set_gauge(self, metric, value, *, attributes=None) -> None:
        return None

    def start_span(self, operation, *, attributes=None) -> _NoOpSpan:
        return _NoOpSpan()

    def shutdown(self) -> None:
        return None


# ---------------------------------------------------------------------------
# In-memory provider (deterministic; for tests + local dashboards)
# ---------------------------------------------------------------------------
@dataclass
class _InMemorySpanRecord:
    operation: str
    attributes: dict[str, str]
    status: SpanStatus = SpanStatus.UNSET
    ended: bool = False


class _InMemorySpan:
    def __init__(self, record: _InMemorySpanRecord, policy: TelemetryAttributePolicy) -> None:
        self._record = record
        self._policy = policy

    def set_status(self, status: SpanStatus) -> None:
        self._record.status = status

    def set_attribute(self, key: str, value: Any) -> None:
        clean = self._policy.sanitize({key: value})
        self._record.attributes.update(clean)

    def end(self) -> None:
        self._record.ended = True


class InMemoryObservabilityProvider:
    """Deterministic capture of metrics and spans for tests/dashboards."""

    def __init__(self, policy: TelemetryAttributePolicy | None = None) -> None:
        self._policy = policy or TelemetryAttributePolicy()
        self.counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self.histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(
            list
        )
        self.gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self.spans: list[_InMemorySpanRecord] = []

    @staticmethod
    def _key(name: str, attributes: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted(attributes.items()))

    def increment(self, metric, *, value=1.0, attributes=None) -> None:
        try:
            clean = self._policy.sanitize(attributes)
            self.counters[self._key(_name(metric), clean)] += float(value)
        except Exception:  # noqa: BLE001 - fail open: never break the caller
            _logger.debug("in-memory increment failed", exc_info=True)

    def record_value(self, metric, value, *, attributes=None) -> None:
        try:
            clean = self._policy.sanitize(attributes)
            self.histograms[self._key(_name(metric), clean)].append(float(value))
        except Exception:  # noqa: BLE001
            _logger.debug("in-memory record failed", exc_info=True)

    def set_gauge(self, metric, value, *, attributes=None) -> None:
        try:
            clean = self._policy.sanitize(attributes)
            self.gauges[self._key(_name(metric), clean)] = float(value)
        except Exception:  # noqa: BLE001
            _logger.debug("in-memory gauge failed", exc_info=True)

    def start_span(self, operation, *, attributes=None) -> _InMemorySpan:
        record = _InMemorySpanRecord(
            operation=operation, attributes=self._policy.sanitize(attributes)
        )
        self.spans.append(record)
        return _InMemorySpan(record, self._policy)

    def shutdown(self) -> None:
        return None

    # --- test/dashboard helpers ---------------------------------------
    def counter_total(self, metric: MetricName, **match: str) -> float:
        name = _name(metric)
        total = 0.0
        for (key_name, attrs), value in self.counters.items():
            if key_name != name:
                continue
            attr_map = dict(attrs)
            if all(attr_map.get(k) == v for k, v in match.items()):
                total += value
        return total

    def histogram_values(self, metric: MetricName, **match: str) -> list[float]:
        name = _name(metric)
        values: list[float] = []
        for (key_name, attrs), samples in self.histograms.items():
            if key_name != name:
                continue
            attr_map = dict(attrs)
            if all(attr_map.get(k) == v for k, v in match.items()):
                values.extend(samples)
        return values

    def gauge_value(self, metric: MetricName, **match: str) -> float | None:
        name = _name(metric)
        for (key_name, attrs), value in self.gauges.items():
            if key_name != name:
                continue
            attr_map = dict(attrs)
            if all(attr_map.get(k) == v for k, v in match.items()):
                return value
        return None

    def reset(self) -> None:
        self.counters.clear()
        self.histograms.clear()
        self.gauges.clear()
        self.spans.clear()


def _name(metric: MetricName | str) -> str:
    return metric.value if isinstance(metric, MetricName) else str(metric)


@contextmanager
def timed_operation(
    provider: ObservabilityProvider,
    operation: str,
    duration_metric: MetricName,
    *,
    attributes: dict[str, Any] | None = None,
):
    """Time a block and record duration in ms; never raises from telemetry."""
    span = provider.start_span(operation, attributes=attributes)
    start = time.perf_counter()
    try:
        yield span
        span.set_status(SpanStatus.OK)
    except Exception:
        span.set_status(SpanStatus.ERROR)
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        try:
            provider.record_value(duration_metric, elapsed_ms, attributes=attributes)
        except Exception:  # noqa: BLE001
            _logger.debug("duration record failed", exc_info=True)
        span.end()
