"""SLO definitions and deterministic evaluation (Phase 3 Prompt 8).

SLOs are versioned, objective, and evaluated deterministically over a window with
a minimum sample count. Critically, the availability indicator is *5xx-free*:
expected 401/403 security denials are NOT counted as failures and therefore never
reduce availability. They belong to separate security-denial indicators.

No production-attainment claim is made from synthetic/local data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.domain.observability_models import SloStatus

# Comparison operators for the objective. Values match the DB check constraint
# (``comparison IN ('gte', 'lte')``) on ent_slo_definitions.
GTE = "gte"  # observed must be >= objective (higher is better)
LTE = "lte"  # observed must be <= objective (lower is better)

# Fraction of the objective gap treated as "at risk" before a breach.
AT_RISK_MARGIN = 0.1


@dataclass(frozen=True, slots=True)
class SloDefinitionSpec:
    slo_key: str
    indicator: str
    objective: float
    comparison: str
    unit: str
    window_seconds: int
    min_sample_count: int
    description: str


def default_slo_definitions() -> list[SloDefinitionSpec]:
    hour = 3600
    return [
        SloDefinitionSpec(
            slo_key="api_availability",
            indicator="api_5xx_free_ratio",
            objective=0.99,
            comparison=GTE,
            unit="ratio",
            window_seconds=24 * hour,
            min_sample_count=20,
            description="Ratio of non-5xx HTTP responses. Excludes expected 401/403.",
        ),
        SloDefinitionSpec(
            slo_key="api_latency_p95",
            indicator="api_latency_p95_ms",
            objective=1500.0,
            comparison=LTE,
            unit="ms",
            window_seconds=24 * hour,
            min_sample_count=20,
            description="95th percentile HTTP request latency.",
        ),
        SloDefinitionSpec(
            slo_key="connector_sync_success",
            indicator="connector_success_ratio",
            objective=0.95,
            comparison=GTE,
            unit="ratio",
            window_seconds=24 * hour,
            min_sample_count=5,
            description="Ratio of successful connector syncs.",
        ),
        SloDefinitionSpec(
            slo_key="ingestion_freshness",
            indicator="fresh_source_ratio",
            objective=0.9,
            comparison=GTE,
            unit="ratio",
            window_seconds=24 * hour,
            min_sample_count=1,
            description="Ratio of sources within their freshness threshold.",
        ),
        SloDefinitionSpec(
            slo_key="audit_write_success",
            indicator="required_audit_write_success_ratio",
            objective=1.0,
            comparison=GTE,
            unit="ratio",
            window_seconds=24 * hour,
            min_sample_count=1,
            description="Ratio of required security-audit writes that succeeded.",
        ),
        SloDefinitionSpec(
            slo_key="ai_schema_valid",
            indicator="ai_schema_valid_ratio",
            objective=1.0,
            comparison=GTE,
            unit="ratio",
            window_seconds=24 * hour,
            min_sample_count=5,
            description="Ratio of AI outputs that were schema-valid (or safely fell back).",
        ),
        SloDefinitionSpec(
            slo_key="ai_citation_correctness",
            indicator="ai_citation_correctness_ratio",
            objective=1.0,
            comparison=GTE,
            unit="ratio",
            window_seconds=24 * hour,
            min_sample_count=5,
            description="Ratio of AI claims with correct citations.",
        ),
    ]


@dataclass(frozen=True, slots=True)
class SloComputation:
    status: SloStatus
    observed_value: float | None
    sample_count: int
    objective: float


def evaluate_slo(
    *,
    observed_value: float | None,
    sample_count: int,
    objective: float,
    comparison: str,
    min_sample_count: int,
    at_risk_margin: float = AT_RISK_MARGIN,
) -> SloComputation:
    if observed_value is None or sample_count < min_sample_count:
        return SloComputation(
            status=SloStatus.INSUFFICIENT_DATA,
            observed_value=observed_value,
            sample_count=sample_count,
            objective=objective,
        )

    if comparison == GTE:
        # "At risk" spans one error-budget below the objective; beyond that is a
        # breach. For a perfect (1.0) objective use the configured margin band.
        budget = (1.0 - objective) if objective < 1.0 else at_risk_margin
        if observed_value >= objective:
            status = SloStatus.HEALTHY
        elif observed_value >= objective - budget:
            status = SloStatus.AT_RISK
        else:
            status = SloStatus.BREACHED
    elif comparison == LTE:
        margin = at_risk_margin * objective
        if observed_value <= objective:
            status = SloStatus.HEALTHY
        elif observed_value <= objective + margin:
            status = SloStatus.AT_RISK
        else:
            status = SloStatus.BREACHED
    else:
        raise ValueError(f"unknown comparison: {comparison}")

    return SloComputation(
        status=status,
        observed_value=observed_value,
        sample_count=sample_count,
        objective=objective,
    )


def slo_canonical_hash(
    *, slo_key: str, slo_version: int, window_start: str, window_end: str, observed: float | None
) -> str:
    payload = {
        "slo_key": slo_key,
        "slo_version": slo_version,
        "window_start": window_start,
        "window_end": window_end,
        "observed": observed,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
