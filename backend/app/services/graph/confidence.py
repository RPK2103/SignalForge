"""Rule-based graph confidence (not Phase 2 assessment confidence).

Graph confidence represents deterministic evidence support for an edge or
finding. It is NOT statistically calibrated and must not be described as a
delivery probability.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.graph_enums import (
    GRAPH_CONFIDENCE_RULE_VERSION,
    GraphDataQualityWarning,
    GraphEdgeOrigin,
)

STALE_AFTER = timedelta(days=90)


def edge_confidence(
    *,
    origin: GraphEdgeOrigin,
    observed_at: datetime,
    now: datetime | None = None,
    repeated_connector_support: bool = False,
    has_explicit_catalog_record: bool = False,
) -> tuple[float, list[GraphDataQualityWarning]]:
    """Return (confidence, warnings) for an edge origin."""
    now = now or datetime.now(timezone.utc)
    # SQLite may round-trip timezone-aware columns as naive UTC.
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    warnings: list[GraphDataQualityWarning] = []
    if origin == GraphEdgeOrigin.MANUAL:
        base = 1.0
    elif origin == GraphEdgeOrigin.CATALOG:
        base = 0.95
    elif origin == GraphEdgeOrigin.CONNECTOR:
        base = 0.85 if repeated_connector_support else 0.75
    elif origin == GraphEdgeOrigin.DERIVED:
        base = 0.55
        if not has_explicit_catalog_record:
            warnings.append(GraphDataQualityWarning.NO_EXPLICIT_DEPENDENCY_RECORD)
    else:
        base = 0.5

    if now - observed_at > STALE_AFTER:
        base = max(0.2, base - 0.2)
        warnings.append(GraphDataQualityWarning.STALE_EVIDENCE)
    return round(base, 4), warnings


def finding_confidence(
    *,
    evidence_count: int,
    has_missing_owner: bool = False,
    is_derived: bool = False,
    has_availability_overlap: bool = False,
) -> tuple[float, list[GraphDataQualityWarning]]:
    warnings: list[GraphDataQualityWarning] = []
    base = 0.6
    if evidence_count >= 3:
        base = 0.85
    elif evidence_count >= 1:
        base = 0.75
    else:
        warnings.append(GraphDataQualityWarning.INSUFFICIENT_HISTORY)
        base = 0.5
    if has_missing_owner:
        warnings.append(GraphDataQualityWarning.MISSING_OWNER)
        base = max(0.3, base - 0.15)
    if is_derived:
        base = min(base, 0.6)
        warnings.append(GraphDataQualityWarning.NO_EXPLICIT_DEPENDENCY_RECORD)
    if has_availability_overlap:
        base = min(1.0, base + 0.05)
    return round(base, 4), warnings


def confidence_rule_version() -> str:
    return GRAPH_CONFIDENCE_RULE_VERSION
