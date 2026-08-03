"""Compute bounded indicator values from captured metrics (Phase 3 Prompt 8).

The dashboard/SLO evaluation reads *aggregates* from the process provider. Only
the deterministic :class:`InMemoryObservabilityProvider` exposes readable state;
with a no-op/OTLP provider the raw metrics live in the telemetry backend, so
these functions honestly report ``None`` (insufficient data) rather than
fabricating values.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider, ObservabilityProvider


def _as_inmemory(provider: ObservabilityProvider) -> InMemoryObservabilityProvider | None:
    return provider if isinstance(provider, InMemoryObservabilityProvider) else None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100.0 * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


@dataclass(frozen=True, slots=True)
class Indicator:
    value: float | None
    sample_count: int


class MetricsReader:
    def __init__(self, provider: ObservabilityProvider) -> None:
        self._mem = _as_inmemory(provider)

    @property
    def available(self) -> bool:
        return self._mem is not None

    # -- HTTP --------------------------------------------------------------
    def http_request_total(self) -> int:
        if self._mem is None:
            return 0
        return int(self._mem.counter_total(MetricName.HTTP_REQUESTS))

    def http_server_errors(self) -> int:
        if self._mem is None:
            return 0
        return int(self._mem.counter_total(MetricName.HTTP_SERVER_ERRORS))

    def http_authentication_denials(self) -> int:
        if self._mem is None:
            return 0
        return int(self._mem.counter_total(MetricName.HTTP_AUTHENTICATION_DENIALS))

    def http_authorization_denials(self) -> int:
        if self._mem is None:
            return 0
        return int(self._mem.counter_total(MetricName.HTTP_AUTHORIZATION_DENIALS))

    def http_latency_percentile(self, pct: float) -> float | None:
        if self._mem is None:
            return None
        return _percentile(self._mem.histogram_values(MetricName.HTTP_REQUEST_DURATION), pct)

    def api_5xx_free_ratio(self) -> Indicator:
        total = self.http_request_total()
        if total == 0:
            return Indicator(None, 0)
        errors = self.http_server_errors()
        # 401/403 are NOT in HTTP_SERVER_ERRORS, so denials never reduce this ratio.
        return Indicator((total - errors) / total, total)

    def api_latency_p95(self) -> Indicator:
        if self._mem is None:
            return Indicator(None, 0)
        values = self._mem.histogram_values(MetricName.HTTP_REQUEST_DURATION)
        return Indicator(_percentile(values, 95), len(values))

    # -- Connectors --------------------------------------------------------
    def connector_success_ratio(self) -> Indicator:
        if self._mem is None:
            return Indicator(None, 0)
        total = int(self._mem.counter_total(MetricName.CONNECTOR_SYNCS))
        if total == 0:
            return Indicator(None, 0)
        success = int(self._mem.counter_total(MetricName.CONNECTOR_SYNCS, outcome="success"))
        return Indicator(success / total, total)

    # -- Audit health ------------------------------------------------------
    def required_audit_write_success_ratio(self) -> Indicator:
        if self._mem is None:
            return Indicator(None, 0)
        required = int(self._mem.counter_total(MetricName.AUDIT_WRITES_REQUIRED))
        if required == 0:
            return Indicator(None, 0)
        succeeded = int(self._mem.counter_total(MetricName.AUDIT_WRITES_SUCCEEDED))
        return Indicator(min(succeeded / required, 1.0), required)

    # -- Chief of Staff / AI ----------------------------------------------
    def ai_schema_valid_ratio(self) -> Indicator:
        if self._mem is None:
            return Indicator(None, 0)
        total = int(self._mem.counter_total(MetricName.COS_GENERATIONS))
        if total == 0:
            return Indicator(None, 0)
        schema_failures = int(self._mem.counter_total(MetricName.COS_SCHEMA_FAILURES))
        fallbacks = int(self._mem.counter_total(MetricName.COS_FALLBACKS))
        # A schema failure that falls back deterministically is still "safe".
        safe = total - max(schema_failures - fallbacks, 0)
        return Indicator(min(safe / total, 1.0), total)

    def fallback_rate(self) -> Indicator:
        if self._mem is None:
            return Indicator(None, 0)
        total = int(self._mem.counter_total(MetricName.COS_GENERATIONS))
        if total == 0:
            return Indicator(None, 0)
        fallbacks = int(self._mem.counter_total(MetricName.COS_FALLBACKS))
        return Indicator(fallbacks / total, total)

    def grounding_failure_rate(self) -> Indicator:
        if self._mem is None:
            return Indicator(None, 0)
        total = int(self._mem.counter_total(MetricName.COS_GENERATIONS))
        if total == 0:
            return Indicator(None, 0)
        failures = int(self._mem.counter_total(MetricName.COS_GROUNDING_FAILURES))
        return Indicator(failures / total, total)

    def cos_review_total(self, *, outcome: str | None = None) -> Indicator:
        """Count Chief-of-Staff / human-review samples (zero → insufficient)."""
        if self._mem is None:
            return Indicator(None, 0)
        if outcome is None:
            total = int(self._mem.counter_total(MetricName.COS_REVIEWS))
        else:
            total = int(self._mem.counter_total(MetricName.COS_REVIEWS, outcome=outcome))
        if total == 0:
            return Indicator(None, 0)
        return Indicator(float(total), total)

    def prediction_validation_total(self, *, outcome: str | None = None) -> Indicator:
        """Count prediction validation-run samples (zero → insufficient)."""
        if self._mem is None:
            return Indicator(None, 0)
        if outcome is None:
            total = int(self._mem.counter_total(MetricName.PREDICTION_VALIDATION_RUNS))
        else:
            total = int(
                self._mem.counter_total(MetricName.PREDICTION_VALIDATION_RUNS, outcome=outcome)
            )
        if total == 0:
            return Indicator(None, 0)
        return Indicator(float(total), total)
