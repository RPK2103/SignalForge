"""Domain telemetry recorders (Phase 3 Prompt 8).

Thin helpers that application services call at their boundaries to emit bounded,
allowlisted metrics through the process observability provider. All recording is
fail-open: a telemetry error is swallowed and never alters deterministic scoring,
security, or the caller's control flow. When observability is disabled the
provider is a no-op, so these calls are free.
"""

from __future__ import annotations

import logging
from typing import Any

from app.observability.metrics import MetricName
from app.observability.runtime import get_observability_provider

_logger = logging.getLogger("signalforge.observability.domain")


def _safe(action) -> None:
    try:
        action()
    except Exception:  # noqa: BLE001 - telemetry never breaks the domain
        _logger.debug("domain telemetry failed", exc_info=True)


def _inc(
    metric: MetricName, *, value: float = 1.0, attributes: dict[str, Any] | None = None
) -> None:
    provider = get_observability_provider()
    _safe(lambda: provider.increment(metric, value=value, attributes=attributes))


def _val(metric: MetricName, value: float, *, attributes: dict[str, Any] | None = None) -> None:
    provider = get_observability_provider()
    _safe(lambda: provider.record_value(metric, value, attributes=attributes))


# ---------------------------------------------------------------------------
# Connector / ingestion
# ---------------------------------------------------------------------------
def record_connector_sync(
    *,
    connector_type: str,
    outcome: str,
    duration_ms: float | None = None,
    observed: int = 0,
    accepted: int = 0,
    deduplicated: int = 0,
    rejected: int = 0,
    retries: int = 0,
    rate_limits: int = 0,
    dead_letters: int = 0,
) -> None:
    attrs = {"connector_type": connector_type, "outcome": outcome}
    _inc(MetricName.CONNECTOR_SYNCS, attributes=attrs)
    if duration_ms is not None:
        _val(MetricName.CONNECTOR_SYNC_DURATION, duration_ms, attributes=attrs)
    if observed:
        _inc(MetricName.CONNECTOR_RECORDS_OBSERVED, value=observed, attributes=attrs)
    if accepted:
        _inc(MetricName.CONNECTOR_RECORDS_ACCEPTED, value=accepted, attributes=attrs)
    if deduplicated:
        _inc(MetricName.CONNECTOR_RECORDS_DEDUPLICATED, value=deduplicated, attributes=attrs)
    if rejected:
        _inc(MetricName.CONNECTOR_RECORDS_REJECTED, value=rejected, attributes=attrs)
    if retries:
        _inc(MetricName.CONNECTOR_RETRIES, value=retries, attributes=attrs)
    if rate_limits:
        _inc(MetricName.CONNECTOR_RATE_LIMITS, value=rate_limits, attributes=attrs)
    if dead_letters:
        _inc(MetricName.CONNECTOR_DEAD_LETTERS, value=dead_letters, attributes=attrs)


def record_ingestion_lag(*, source_type: str, lag_seconds: float) -> None:
    _val(
        MetricName.CONNECTOR_INGESTION_LAG,
        lag_seconds,
        attributes={"source_type": source_type},
    )


def record_freshness_age(*, source_type: str, freshness_state: str, age_seconds: float) -> None:
    _val(
        MetricName.CONNECTOR_FRESHNESS_AGE,
        age_seconds,
        attributes={"source_type": source_type, "freshness_state": freshness_state},
    )


# ---------------------------------------------------------------------------
# Delivery graph
# ---------------------------------------------------------------------------
def record_graph_rebuild(
    *, outcome: str, duration_ms: float | None = None, incremental: bool = False
) -> None:
    attrs = {"outcome": outcome}
    if incremental:
        _inc(MetricName.GRAPH_INCREMENTAL_UPDATES, attributes=attrs)
    else:
        _inc(MetricName.GRAPH_REBUILDS, attributes=attrs)
    if duration_ms is not None:
        _val(MetricName.GRAPH_DURATION, duration_ms, attributes=attrs)
    if outcome not in ("success",):
        _inc(MetricName.GRAPH_FAILED_REBUILDS, attributes=attrs)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
def record_prediction(
    *,
    model_version: str,
    outcome: str,
    duration_ms: float | None = None,
    fallback: bool = False,
    missing_data: bool = False,
) -> None:
    attrs = {"model_version": model_version, "outcome": outcome}
    _inc(MetricName.PREDICTIONS, attributes=attrs)
    if duration_ms is not None:
        _val(MetricName.PREDICTION_DURATION, duration_ms, attributes=attrs)
    if fallback:
        _inc(MetricName.PREDICTION_FALLBACKS, attributes=attrs)
    if missing_data:
        _inc(MetricName.PREDICTION_MISSING_DATA, attributes=attrs)


def record_prediction_validation(
    *,
    model_version: str,
    outcome: str,
    evaluation_type: str | None = None,
) -> None:
    attrs: dict[str, str] = {"model_version": model_version, "outcome": outcome}
    if evaluation_type:
        attrs["evaluation_type"] = evaluation_type
    _inc(MetricName.PREDICTION_VALIDATION_RUNS, attributes=attrs)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def record_scenario_run(
    *,
    scenario_kind: str,
    outcome: str,
    duration_ms: float | None = None,
    fallback: bool = False,
    validation_failure: bool = False,
) -> None:
    attrs = {"scenario_kind": scenario_kind, "outcome": outcome}
    _inc(MetricName.SCENARIO_RUNS, attributes=attrs)
    if duration_ms is not None:
        _val(MetricName.SCENARIO_DURATION, duration_ms, attributes=attrs)
    if fallback:
        _inc(MetricName.SCENARIO_FALLBACKS, attributes=attrs)
    if validation_failure:
        _inc(MetricName.SCENARIO_VALIDATION_FAILURES, attributes=attrs)


# ---------------------------------------------------------------------------
# Chief of Staff / AI provider
# ---------------------------------------------------------------------------
def record_cos_generation(
    *,
    provider_type: str,
    outcome: str,
    fallback_category: str | None = None,
    provider_latency_ms: float | None = None,
    fallback: bool = False,
    parse_failure: bool = False,
    schema_failure: bool = False,
    grounding_failure: bool = False,
    unsupported_claim: bool = False,
    citation_failure: bool = False,
) -> None:
    attrs = {"provider_type": provider_type, "outcome": outcome}
    if fallback_category:
        attrs["fallback_category"] = fallback_category
    _inc(MetricName.COS_GENERATIONS, attributes=attrs)
    if provider_latency_ms is not None:
        _val(MetricName.COS_PROVIDER_LATENCY, provider_latency_ms, attributes=attrs)
    if fallback:
        _inc(MetricName.COS_FALLBACKS, attributes=attrs)
    if parse_failure:
        _inc(MetricName.COS_PARSE_FAILURES, attributes=attrs)
    if schema_failure:
        _inc(MetricName.COS_SCHEMA_FAILURES, attributes=attrs)
    if grounding_failure:
        _inc(MetricName.COS_GROUNDING_FAILURES, attributes=attrs)
    if unsupported_claim:
        _inc(MetricName.COS_UNSUPPORTED_CLAIM_REJECTIONS, attributes=attrs)
    if citation_failure:
        _inc(MetricName.COS_CITATION_FAILURES, attributes=attrs)


def record_cos_review(*, outcome: str) -> None:
    _inc(MetricName.COS_REVIEWS, attributes={"outcome": outcome})


# ---------------------------------------------------------------------------
# Security audit health
# ---------------------------------------------------------------------------
def record_audit_write(
    *, required: bool, succeeded: bool | None = None, fail_closed: bool = False
) -> None:
    """Record audit-write health.

    ``succeeded=None`` increments only the required counter (used when success
    is deferred until a durable UnitOfWork commit). ``succeeded=True/False``
    records the terminal outcome immediately.
    """
    if required:
        _inc(MetricName.AUDIT_WRITES_REQUIRED)
    if succeeded is True:
        _inc(MetricName.AUDIT_WRITES_SUCCEEDED)
    elif succeeded is False:
        _inc(MetricName.AUDIT_WRITES_FAILED)
    if fail_closed:
        _inc(MetricName.AUDIT_FAIL_CLOSED_MUTATIONS)


def record_audit_succeeded() -> None:
    """Emit a single audit-write success sample (post-commit only)."""
    _inc(MetricName.AUDIT_WRITES_SUCCEEDED)
