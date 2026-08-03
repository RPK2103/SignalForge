"""OpenTelemetry-backed observability provider (Prompt 8).

Only constructed at the application edge when ``OTEL_EXPORTER_MODE`` is
``console`` or ``otlp``. Imports the OpenTelemetry SDK lazily so unit tests never
depend on it and a missing SDK degrades gracefully (see ``runtime.build_provider``).

Hard privacy/cardinality guarantees:
- attributes always pass through :class:`TelemetryAttributePolicy` first;
- no request body, authorization header, cookie, SQL parameter, prompt, evidence
  payload or connector credential is ever set as a span/metric attribute;
- exporter timeout and batch queue/export sizes are bounded from settings;
- exporter failure is graceful (SDK batch processor drops on error) and never
  raises into a user request.

OTLP exporter headers are resolved through an approved secret-reference boundary
(an env-var name given by ``OTEL_EXPORTER_OTLP_HEADERS_SECRET_REF``) — the raw
header value is never stored in settings.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.core.config import Settings
from app.observability.attributes import TelemetryAttributePolicy
from app.observability.metrics import MetricName, SpanStatus

_logger = logging.getLogger("signalforge.observability")

_HISTOGRAM_METRICS = frozenset(
    {
        MetricName.HTTP_REQUEST_DURATION,
        MetricName.CONNECTOR_SYNC_DURATION,
        MetricName.GRAPH_DURATION,
        MetricName.PREDICTION_DURATION,
        MetricName.SCENARIO_DURATION,
        MetricName.COS_PROVIDER_LATENCY,
        MetricName.CONNECTOR_INGESTION_LAG,
        MetricName.CONNECTOR_FRESHNESS_AGE,
    }
)
_GAUGE_METRICS = frozenset({MetricName.HTTP_ACTIVE_REQUESTS})


def _resolve_otlp_headers(secret_ref: str) -> dict[str, str]:
    """Resolve exporter headers from the referenced secret (env var), never raw."""
    if not secret_ref:
        return {}
    raw = os.environ.get(secret_ref, "")
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                headers[key] = value
    return headers


class _OtelSpan:
    def __init__(self, span: Any, policy: TelemetryAttributePolicy) -> None:
        self._span = span
        self._policy = policy

    def set_status(self, status: SpanStatus) -> None:
        try:
            from opentelemetry.trace import Status, StatusCode

            code = {
                SpanStatus.OK: StatusCode.OK,
                SpanStatus.ERROR: StatusCode.ERROR,
                SpanStatus.UNSET: StatusCode.UNSET,
            }[status]
            self._span.set_status(Status(code))
        except Exception:  # noqa: BLE001
            _logger.debug("span set_status failed", exc_info=True)

    def set_attribute(self, key: str, value: Any) -> None:
        clean = self._policy.sanitize({key: value})
        for k, v in clean.items():
            try:
                self._span.set_attribute(k, v)
            except Exception:  # noqa: BLE001
                _logger.debug("span set_attribute failed", exc_info=True)

    def end(self) -> None:
        try:
            self._span.end()
        except Exception:  # noqa: BLE001
            _logger.debug("span end failed", exc_info=True)


class OpenTelemetryObservabilityProvider:
    def __init__(self, settings: Settings) -> None:
        # Imports here so the module import (and unit tests) never require the SDK.
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        self._policy = TelemetryAttributePolicy()
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": settings.otel_service_version,
                "deployment.environment": settings.app_env,
            }
        )

        span_exporter, metric_exporter = self._build_exporters(settings)

        self._tracer_provider = TracerProvider(
            resource=resource,
            sampler=TraceIdRatioBased(settings.otel_trace_sample_ratio),
        )
        if span_exporter is not None:
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    span_exporter,
                    max_queue_size=settings.otel_batch_max_queue_size,
                    max_export_batch_size=settings.otel_batch_max_export_size,
                    export_timeout_millis=settings.otel_export_timeout_seconds * 1000,
                )
            )
        self._tracer = trace.get_tracer("signalforge", tracer_provider=self._tracer_provider)

        readers = []
        if metric_exporter is not None:
            readers.append(
                PeriodicExportingMetricReader(
                    metric_exporter,
                    export_interval_millis=settings.metric_rollup_interval_seconds * 1000,
                    export_timeout_millis=settings.otel_export_timeout_seconds * 1000,
                )
            )
        self._meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        meter = self._meter_provider.get_meter("signalforge")

        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._gauges: dict[str, float] = {}
        self._meter = meter
        _ = metrics  # keep import referenced

    @staticmethod
    def _build_exporters(settings: Settings):
        if settings.otel_exporter_mode == "console":
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            return ConsoleSpanExporter(), ConsoleMetricExporter()
        if settings.otel_exporter_mode == "otlp":
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            headers = _resolve_otlp_headers(settings.otel_exporter_otlp_headers_secret_ref)
            timeout = settings.otel_export_timeout_seconds
            endpoint = settings.otel_exporter_otlp_endpoint
            return (
                OTLPSpanExporter(
                    endpoint=f"{endpoint}/v1/traces", headers=headers, timeout=timeout
                ),
                OTLPMetricExporter(
                    endpoint=f"{endpoint}/v1/metrics", headers=headers, timeout=timeout
                ),
            )
        return None, None

    def _counter(self, name: str):
        counter = self._counters.get(name)
        if counter is None:
            counter = self._meter.create_counter(name)
            self._counters[name] = counter
        return counter

    def _histogram(self, name: str):
        hist = self._histograms.get(name)
        if hist is None:
            hist = self._meter.create_histogram(name)
            self._histograms[name] = hist
        return hist

    def increment(self, metric, *, value=1.0, attributes=None) -> None:
        try:
            clean = self._policy.sanitize(attributes)
            self._counter(metric.value if isinstance(metric, MetricName) else str(metric)).add(
                value, clean
            )
        except Exception:  # noqa: BLE001 - fail open
            _logger.debug("otel increment failed", exc_info=True)

    def record_value(self, metric, value, *, attributes=None) -> None:
        try:
            clean = self._policy.sanitize(attributes)
            self._histogram(metric.value if isinstance(metric, MetricName) else str(metric)).record(
                value, clean
            )
        except Exception:  # noqa: BLE001
            _logger.debug("otel record failed", exc_info=True)

    def set_gauge(self, metric, value, *, attributes=None) -> None:
        # Represent gauges as histograms of the latest value; keeps the exporter
        # simple and avoids async observable callbacks in a request path.
        self.record_value(metric, value, attributes=attributes)

    def start_span(self, operation, *, attributes=None):
        try:
            span = self._tracer.start_span(operation)
            wrapped = _OtelSpan(span, self._policy)
            if attributes:
                for key, val in attributes.items():
                    wrapped.set_attribute(key, val)
            return wrapped
        except Exception:  # noqa: BLE001
            from app.observability.provider import _NoOpSpan

            return _NoOpSpan()

    def shutdown(self) -> None:
        for provider in (self._tracer_provider, self._meter_provider):
            try:
                provider.shutdown()
            except Exception:  # noqa: BLE001 - deterministic shutdown, never raise
                _logger.debug("otel provider shutdown failed", exc_info=True)
