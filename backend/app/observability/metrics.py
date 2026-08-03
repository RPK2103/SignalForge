"""Metric names and shared telemetry enums (Prompt 8).

Metric instrument names are a bounded, reviewed taxonomy. Keeping them here (not
inline strings) prevents accidental proliferation and typos across services.
"""

from __future__ import annotations

from enum import Enum


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class OperationOutcome(str, Enum):
    """Business/technical outcome of an instrumented operation.

    Note the deliberate separation of security denials from server failures:
    an authentication or authorization denial is an expected security outcome,
    NOT an availability/server failure.
    """

    SUCCESS = "success"
    CLIENT_ERROR = "client_error"  # 4xx domain/validation
    AUTHENTICATION_DENIED = "authentication_denied"  # 401
    AUTHORIZATION_DENIED = "authorization_denied"  # 403
    RATE_LIMITED = "rate_limited"  # 429
    SERVER_ERROR = "server_error"  # 5xx / unhandled
    CANCELLED = "cancelled"
    FALLBACK = "fallback"
    REJECTED = "rejected"
    INSUFFICIENT_DATA = "insufficient_data"


class MetricName(str, Enum):
    # HTTP request telemetry
    HTTP_REQUESTS = "http.server.requests"
    HTTP_REQUEST_DURATION = "http.server.duration_ms"
    HTTP_ACTIVE_REQUESTS = "http.server.active_requests"
    HTTP_SERVER_ERRORS = "http.server.errors"  # 5xx / unhandled ONLY
    HTTP_UNHANDLED_EXCEPTIONS = "http.server.unhandled_exceptions"
    HTTP_CANCELLATIONS = "http.server.cancellations"
    HTTP_AUTHENTICATION_DENIALS = "http.server.authentication_denials"  # 401
    HTTP_AUTHORIZATION_DENIALS = "http.server.authorization_denials"  # 403
    HTTP_RATE_LIMITS = "http.server.rate_limits"  # 429
    HTTP_DB_TIMEOUTS = "http.server.db_timeouts"

    # Connector / ingestion telemetry
    CONNECTOR_SYNCS = "connector.syncs"
    CONNECTOR_SYNC_DURATION = "connector.sync.duration_ms"
    CONNECTOR_RECORDS_OBSERVED = "connector.records.observed"
    CONNECTOR_RECORDS_ACCEPTED = "connector.records.accepted"
    CONNECTOR_RECORDS_DEDUPLICATED = "connector.records.deduplicated"
    CONNECTOR_RECORDS_REJECTED = "connector.records.rejected"
    CONNECTOR_RETRIES = "connector.retries"
    CONNECTOR_RATE_LIMITS = "connector.rate_limits"
    CONNECTOR_DEAD_LETTERS = "connector.dead_letters"
    CONNECTOR_INGESTION_LAG = "connector.ingestion.lag_seconds"
    CONNECTOR_FRESHNESS_AGE = "connector.evidence.freshness_age_seconds"

    # Delivery graph telemetry
    GRAPH_REBUILDS = "graph.rebuilds"
    GRAPH_INCREMENTAL_UPDATES = "graph.incremental_updates"
    GRAPH_DURATION = "graph.duration_ms"
    GRAPH_FAILED_REBUILDS = "graph.failed_rebuilds"

    # Prediction telemetry
    PREDICTIONS = "prediction.predictions"
    PREDICTION_DURATION = "prediction.duration_ms"
    PREDICTION_FALLBACKS = "prediction.fallbacks"
    PREDICTION_MISSING_DATA = "prediction.missing_data"
    PREDICTION_VALIDATION_RUNS = "prediction.validation_runs"

    # Scenario telemetry
    SCENARIO_RUNS = "scenario.runs"
    SCENARIO_DURATION = "scenario.duration_ms"
    SCENARIO_FALLBACKS = "scenario.fallbacks"
    SCENARIO_VALIDATION_FAILURES = "scenario.validation_failures"

    # Chief of Staff / AI provider telemetry
    COS_GENERATIONS = "cos.generations"
    COS_PROVIDER_LATENCY = "cos.provider.latency_ms"
    COS_FALLBACKS = "cos.fallbacks"
    COS_PARSE_FAILURES = "cos.parse_failures"
    COS_SCHEMA_FAILURES = "cos.schema_failures"
    COS_GROUNDING_FAILURES = "cos.grounding_failures"
    COS_UNSUPPORTED_CLAIM_REJECTIONS = "cos.unsupported_claim_rejections"
    COS_CITATION_FAILURES = "cos.citation_failures"
    COS_REVIEWS = "cos.reviews"

    # Security audit health telemetry
    AUDIT_WRITES_REQUIRED = "audit.writes.required"
    AUDIT_WRITES_SUCCEEDED = "audit.writes.succeeded"
    AUDIT_WRITES_FAILED = "audit.writes.failed"
    AUDIT_FAIL_CLOSED_MUTATIONS = "audit.fail_closed_mutations"

    # Telemetry self-health
    TELEMETRY_EXPORT_FAILURES = "telemetry.export_failures"
