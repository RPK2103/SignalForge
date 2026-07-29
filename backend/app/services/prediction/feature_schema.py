"""Versioned delivery feature dictionary (delivery_features_v1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.domain.prediction_constants import FEATURE_SCHEMA_VERSION, FORBIDDEN_FEATURE_TOKENS
from app.services.persistence.snapshot_service import snapshot_hash

MissingPolicy = Literal["zero", "mean_train", "flag_only"]
LeakageRisk = Literal["low", "medium", "high"]
FeatureValueType = Literal["float"]


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    type: FeatureValueType
    allowed_range: tuple[float | None, float | None]
    missing_policy: MissingPolicy
    transformation: str
    source: str
    leakage_risk: LeakageRisk
    human_description: str


def _f(
    name: str,
    *,
    lo: float | None,
    hi: float | None,
    missing: MissingPolicy,
    transformation: str,
    source: str,
    leakage: LeakageRisk,
    description: str,
) -> FeatureDefinition:
    return FeatureDefinition(
        name=name,
        type="float",
        allowed_range=(lo, hi),
        missing_policy=missing,
        transformation=transformation,
        source=source,
        leakage_risk=leakage,
        human_description=description,
    )


FEATURE_DEFINITIONS: list[FeatureDefinition] = [
    # A. Delivery readiness (Phase 2 snapshot read-only; never recomputed)
    _f(
        "readiness_score_at_cutoff",
        lo=0.0,
        hi=100.0,
        missing="flag_only",
        transformation="identity",
        source="assessment.readiness_score",
        leakage="low",
        description="Phase 2 readiness score from latest assessment at or before cutoff.",
    ),
    _f(
        "assessment_confidence_at_cutoff",
        lo=0.0,
        hi=100.0,
        missing="flag_only",
        transformation="identity",
        source="assessment.confidence_score",
        leakage="low",
        description="Phase 2 assessment confidence score (separate from readiness).",
    ),
    _f(
        "capability_coverage",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="clip_unit",
        source="capability_requirements+ownership",
        leakage="low",
        description="Fraction of required capabilities with at least one active owner at cutoff.",
    ),
    _f(
        "critical_capability_gap_count",
        lo=0.0,
        hi=100.0,
        missing="zero",
        transformation="count",
        source="capability_requirements+ownership",
        leakage="low",
        description="Count of critical required capabilities lacking an active owner at cutoff.",
    ),
    _f(
        "unresolved_critical_risk_count",
        lo=0.0,
        hi=100.0,
        missing="zero",
        transformation="count",
        source="assessment_risk_findings",
        leakage="low",
        description="Critical assessment risk findings on the readiness snapshot at cutoff.",
    ),
    # B. Delivery graph
    _f(
        "active_dependency_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.edges.depends_on",
        leakage="medium",
        description="Active DEPENDS_ON/BLOCKS edges touching the target node at cutoff.",
    ),
    _f(
        "dependency_depth",
        lo=0.0,
        hi=20.0,
        missing="zero",
        transformation="bfs_depth",
        source="graph.edges.depends_on",
        leakage="medium",
        description="Maximum outbound dependency depth from the target at cutoff (bounded BFS).",
    ),
    _f(
        "cross_team_dependency_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings.cross_team_dependency",
        leakage="medium",
        description="Active cross-team dependency findings affecting the target at cutoff.",
    ),
    _f(
        "active_dependency_cycle_indicator",
        lo=0.0,
        hi=1.0,
        missing="zero",
        transformation="indicator",
        source="graph.findings.dependency_cycle",
        leakage="medium",
        description="1 if an active dependency-cycle finding affects the target at cutoff.",
    ),
    _f(
        "repository_ownership_concentration_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings.repository_ownership_concentration",
        leakage="medium",
        description="Active repository ownership concentration findings affecting the target.",
    ),
    _f(
        "capability_ownership_concentration_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings.capability_ownership_concentration",
        leakage="medium",
        description="Active capability ownership concentration findings affecting the target.",
    ),
    _f(
        "single_person_dependency_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings.single_person_dependency",
        leakage="medium",
        description="Active single-person dependency findings affecting the target.",
    ),
    _f(
        "availability_blast_radius_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings.availability_blast_radius",
        leakage="medium",
        description="Active availability blast-radius findings affecting the target.",
    ),
    _f(
        "affected_critical_initiative_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings+initiatives",
        leakage="medium",
        description="Critical initiatives in the blast radius of findings for the target.",
    ),
    _f(
        "finding_severity_critical_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings",
        leakage="medium",
        description="Active critical-severity graph findings affecting the target at cutoff.",
    ),
    _f(
        "finding_severity_high_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings",
        leakage="medium",
        description="Active high-severity graph findings affecting the target at cutoff.",
    ),
    _f(
        "finding_severity_medium_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings",
        leakage="medium",
        description="Active medium-severity graph findings affecting the target at cutoff.",
    ),
    _f(
        "finding_severity_low_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings",
        leakage="medium",
        description="Active low-severity graph findings affecting the target at cutoff.",
    ),
    # C. Ownership / team resilience
    _f(
        "active_engineer_owner_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="ownership",
        leakage="low",
        description="Distinct engineer owners of the target (or its resources) active at cutoff.",
    ),
    _f(
        "active_team_owner_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="ownership",
        leakage="low",
        description="Distinct team owners of the target (or its resources) active at cutoff.",
    ),
    _f(
        "ownership_redundancy",
        lo=0.0,
        hi=100.0,
        missing="mean_train",
        transformation="ratio",
        source="ownership",
        leakage="low",
        description="Average owners per owned resource for the target scope at cutoff.",
    ),
    _f(
        "critical_capability_owner_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="ownership+capability_requirements",
        leakage="low",
        description="Distinct owners of critical required capabilities for the target.",
    ),
    _f(
        "unavailable_owner_ratio",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="clip_unit",
        source="ownership+availability",
        leakage="medium",
        description="Fraction of engineer owners with reduced availability overlapping cutoff.",
    ),
    _f(
        "team_availability_ratio",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="clip_unit",
        source="availability",
        leakage="medium",
        description="Mean team availability percentage (0-1) for participating teams at cutoff.",
    ),
    _f(
        "unresolved_actor_identity_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph.findings+data_quality",
        leakage="low",
        description="Unresolved actor-identity data-quality warnings affecting the target.",
    ),
    # D. Workflow / delivery flow
    _f(
        "open_work_item_count",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count",
        source="work_items",
        leakage="low",
        description="Open work items for the target with source timestamps at or before cutoff.",
    ),
    _f(
        "overdue_work_item_count",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count",
        source="work_items+sprints",
        leakage="low",
        description="Open work items whose sprint end_time is before cutoff.",
    ),
    _f(
        "blocked_work_item_count",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count",
        source="work_items+graph.edges.blocks",
        leakage="medium",
        description="Open work items with an active BLOCKS edge at cutoff.",
    ),
    _f(
        "work_item_aging_days_avg",
        lo=0.0,
        hi=3650.0,
        missing="mean_train",
        transformation="mean_days",
        source="work_items",
        leakage="low",
        description="Average age in days of open work items at cutoff.",
    ),
    _f(
        "sprint_completion_ratio",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="clip_unit",
        source="work_items+sprints",
        leakage="low",
        description="Done/(done+open) ratio for work items in sprints ending by cutoff.",
    ),
    _f(
        "pr_open_count",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count",
        source="pull_requests",
        leakage="low",
        description="Open pull requests linked to target repositories created at or before cutoff.",
    ),
    _f(
        "pr_age_days_avg",
        lo=0.0,
        hi=3650.0,
        missing="mean_train",
        transformation="mean_days",
        source="pull_requests",
        leakage="low",
        description="Average age in days of open pull requests at cutoff.",
    ),
    _f(
        "review_latency_days_avg",
        lo=0.0,
        hi=3650.0,
        missing="mean_train",
        transformation="mean_days",
        source="pull_requests+graph.edges.reviews",
        leakage="medium",
        description="Average days from PR open to first review or merge (closed by cutoff).",
    ),
    _f(
        "unreviewed_pr_count",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count",
        source="pull_requests+graph.edges.reviews",
        leakage="medium",
        description="Open PRs at cutoff with no REVIEWS edge observed at or before cutoff.",
    ),
    _f(
        "deployment_count_30d",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count_window",
        source="deployments",
        leakage="low",
        description="Deployments started in the 30 days ending at cutoff for the target.",
    ),
    _f(
        "failed_deployment_count_30d",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count_window",
        source="deployments",
        leakage="low",
        description="Failed/rolled-back deployments in the 30 days ending at cutoff.",
    ),
    _f(
        "incident_count_30d",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count_window",
        source="incidents",
        leakage="low",
        description="Incidents started in the 30 days ending at cutoff for the target.",
    ),
    _f(
        "unresolved_incident_count",
        lo=0.0,
        hi=100_000.0,
        missing="zero",
        transformation="count",
        source="incidents",
        leakage="low",
        description="Incidents started at or before cutoff that remain unresolved at cutoff.",
    ),
    # E. Data quality / freshness
    _f(
        "evidence_freshness_age_hours",
        lo=0.0,
        hi=876_000.0,
        missing="flag_only",
        transformation="hours_since",
        source="evidence_signals",
        leakage="low",
        description="Hours between as_of_at and the newest evidence observed_at <= cutoff.",
    ),
    _f(
        "source_coverage_ratio",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="clip_unit",
        source="data_sources",
        leakage="low",
        description="Fraction of data sources with a successful sync at or before cutoff.",
    ),
    _f(
        "stale_source_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="data_sources",
        leakage="low",
        description="Data sources marked stale or aging relative to cutoff.",
    ),
    _f(
        "missing_team_mapping_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="graph+projects",
        leakage="low",
        description="Work items/repos in scope without a team mapping at cutoff.",
    ),
    _f(
        "missing_owner_indicator",
        lo=0.0,
        hi=1.0,
        missing="zero",
        transformation="indicator",
        source="ownership",
        leakage="low",
        description="1 if the target has no active engineer or team owner at cutoff.",
    ),
    _f(
        "incomplete_history_indicator",
        lo=0.0,
        hi=1.0,
        missing="zero",
        transformation="indicator",
        source="evidence_signals+work_items",
        leakage="low",
        description="1 when evidence volume or workflow history is below a minimum threshold.",
    ),
    _f(
        "graph_projection_age_hours",
        lo=0.0,
        hi=876_000.0,
        missing="flag_only",
        transformation="hours_since",
        source="graph.projection_runs",
        leakage="low",
        description="Hours from as_of_at to latest successful graph projection at/before cutoff.",
    ),
    _f(
        "evidence_volume_30d",
        lo=0.0,
        hi=1_000_000.0,
        missing="zero",
        transformation="count_window",
        source="evidence_signals",
        leakage="low",
        description="Evidence signals for the target observed in the 30 days ending at cutoff.",
    ),
    # F. Project context
    _f(
        "project_criticality_score",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="ordinal_map",
        source="projects.criticality",
        leakage="low",
        description="Mapped project criticality (critical=1 .. low=0.25).",
    ),
    _f(
        "initiative_criticality_score",
        lo=0.0,
        hi=1.0,
        missing="mean_train",
        transformation="ordinal_map",
        source="initiatives.criticality",
        leakage="low",
        description="Mapped initiative criticality (critical=1 .. low=0.25).",
    ),
    _f(
        "planned_duration_days",
        lo=0.0,
        hi=3650.0,
        missing="mean_train",
        transformation="days",
        source="projects|initiatives.planned_*",
        leakage="low",
        description="Planned duration in days from planned_start to planned_target.",
    ),
    _f(
        "participating_team_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="ownership+work_items",
        leakage="low",
        description="Distinct teams participating via ownership or work items at cutoff.",
    ),
    _f(
        "repository_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="ownership+repositories",
        leakage="low",
        description="Distinct repositories linked to the target at cutoff.",
    ),
    _f(
        "required_capability_count",
        lo=0.0,
        hi=10_000.0,
        missing="zero",
        transformation="count",
        source="capability_requirements",
        leakage="low",
        description="Number of capability requirements declared for the target.",
    ),
    _f(
        "project_age_days_at_cutoff",
        lo=0.0,
        hi=3650.0,
        missing="mean_train",
        transformation="days",
        source="projects|initiatives.planned_start",
        leakage="low",
        description="Days from planned_start (or created proxy) to cutoff.",
    ),
]

FEATURE_NAMES: list[str] = [f.name for f in FEATURE_DEFINITIONS]
_FEATURE_BY_NAME: dict[str, FeatureDefinition] = {f.name: f for f in FEATURE_DEFINITIONS}

assert len(FEATURE_NAMES) == len(_FEATURE_BY_NAME), "Duplicate feature names in schema"
assert FEATURE_SCHEMA_VERSION == "delivery_features_v1"


def feature_schema_hash() -> str:
    payload = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": [asdict(f) for f in FEATURE_DEFINITIONS],
    }
    return snapshot_hash(payload)


def get_feature_meta(name: str) -> FeatureDefinition | None:
    return _FEATURE_BY_NAME.get(name)


def validate_feature_values(values: dict[str, Any]) -> list[str]:
    """Return non-fatal warnings for a feature value map."""
    warnings: list[str] = []
    for key in values:
        lowered = key.lower()
        for token in FORBIDDEN_FEATURE_TOKENS:
            if token in lowered:
                warnings.append(f"forbidden_feature_token:{key}")
                break
        if key in {
            "binary_label",
            "outcome_category",
            "actual_completed_at",
            "probability_of_delivery_success",
        }:
            warnings.append(f"leakage_feature:{key}")

    for name, meta in _FEATURE_BY_NAME.items():
        if name not in values:
            warnings.append(f"missing_feature:{name}")
            continue
        raw = values[name]
        if raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            warnings.append(f"non_numeric:{name}")
            continue
        if number != number or number in (float("inf"), float("-inf")):  # noqa: PLR0124
            warnings.append(f"non_finite:{name}")
            continue
        lo, hi = meta.allowed_range
        if lo is not None and number < lo:
            warnings.append(f"below_range:{name}")
        if hi is not None and number > hi:
            warnings.append(f"above_range:{name}")

    for name in values:
        if name not in _FEATURE_BY_NAME and name not in {
            "binary_label",
            "outcome_category",
            "actual_completed_at",
            "probability_of_delivery_success",
        }:
            warnings.append(f"unknown_feature:{name}")
    return warnings
