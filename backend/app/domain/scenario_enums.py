"""Continuous Scenario Intelligence enums (Phase 3 Prompt 5)."""

from enum import Enum


class ScenarioKind(str, Enum):
    ENGINEER_UNAVAILABLE = "engineer_unavailable"
    TEAM_CAPACITY_REDUCTION = "team_capacity_reduction"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"
    DEPENDENCY_DELAY = "dependency_delay"
    DEADLINE_COMPRESSION = "deadline_compression"
    INCIDENT_ESCALATION = "incident_escalation"
    COMBINED = "combined"


class ScenarioLifecycleState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DISABLED = "disabled"


class ScenarioTargetType(str, Enum):
    PROJECT = "project"
    INITIATIVE = "initiative"


class ScenarioRunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED_NO_CHANGE = "skipped_no_change"


class ScenarioRunMode(str, Enum):
    MANUAL = "manual"
    WATCH = "watch"
    IDEMPOTENT_REUSE = "idempotent_reuse"


class ScenarioWatchMode(str, Enum):
    MANUAL = "manual"
    ON_CHANGE = "on_change"


class ScenarioWatchLifecycle(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ScenarioTriggerReason(str, Enum):
    SCENARIO_VERSION_CHANGED = "scenario_version_changed"
    TARGET_CHANGED = "target_changed"
    OWNERSHIP_CHANGED = "ownership_changed"
    DEPENDENCY_CHANGED = "dependency_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    GRAPH_PROJECTION_CHANGED = "graph_projection_changed"
    GRAPH_FINDINGS_CHANGED = "graph_findings_changed"
    PREDICTION_MODEL_CHANGED = "prediction_model_changed"
    PREDICTION_BASELINE_CHANGED = "prediction_baseline_changed"
    RELEVANT_EVIDENCE_CHANGED = "relevant_evidence_changed"
    SOURCE_FRESHNESS_CHANGED = "source_freshness_changed"
    MANUAL_REQUEST = "manual_request"
    NO_RELEVANT_CHANGE = "no_relevant_change"
    MINIMUM_INTERVAL_NOT_ELAPSED = "minimum_interval_not_elapsed"


class ScenarioTriggerAction(str, Enum):
    EVALUATED = "evaluated"
    SKIPPED_NO_CHANGE = "skipped_no_change"
    SKIPPED_INTERVAL = "skipped_interval"
    FAILED = "failed"


class EstimateComparability(str, Enum):
    COMPARABLE_PROBABILITY = "comparable_probability"
    COMPARABLE_SCORE = "comparable_score"
    INCOMPARABLE_ESTIMATE_KIND = "incomparable_estimate_kind"
    INSUFFICIENT_DATA = "insufficient_data"


class ScenarioImpactType(str, Enum):
    NODE_AFFECTED = "node_affected"
    PATH_AFFECTED = "path_affected"
    INITIATIVE_AFFECTED = "initiative_affected"
    PROJECT_AFFECTED = "project_affected"
    OWNERSHIP_CONCENTRATION_INCREASED = "ownership_concentration_increased"
    CAPABILITY_CONCENTRATION_INCREASED = "capability_concentration_increased"
    DEPENDENCY_DELAY_INTRODUCED = "dependency_delay_introduced"
    CYCLE_CREATED = "cycle_created"
    CYCLE_REMOVED = "cycle_removed"
    FINDING_ADDED = "finding_added"
    FINDING_REMOVED = "finding_removed"
    FINDING_SEVERITY_CHANGED = "finding_severity_changed"
    PREDICTION_SCORE_CHANGED = "prediction_score_changed"
    PREDICTION_PROBABILITY_CHANGED = "prediction_probability_changed"
    ESTIMATE_INCOMPARABLE = "estimate_incomparable"
    DATA_QUALITY_DEGRADED = "data_quality_degraded"


class ImpactDirection(str, Enum):
    WORSENED = "worsened"
    IMPROVED = "improved"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class ImpactSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScenarioImpactConfidence(str, Enum):
    """Support for a deterministic scenario impact — not Phase 2/3/4 confidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNSUPPORTED = "unsupported"


class ComparisonDimension(str, Enum):
    AFFECTED_PROJECT_COUNT = "affected_project_count"
    AFFECTED_INITIATIVE_COUNT = "affected_initiative_count"
    AFFECTED_CRITICAL_INITIATIVE_COUNT = "affected_critical_initiative_count"
    GRAPH_FINDINGS_ADDED = "graph_findings_added"
    GRAPH_FINDINGS_WORSENED = "graph_findings_worsened"
    OWNERSHIP_CONCENTRATION_CHANGE = "ownership_concentration_change"
    CAPABILITY_CONCENTRATION_CHANGE = "capability_concentration_change"
    DEPENDENCY_DELAY = "dependency_delay"
    RISK_SCORE_DELTA = "risk_score_delta"
    PROBABILITY_DELTA = "probability_delta"
    DATA_QUALITY_DEGRADATION = "data_quality_degradation"


class SimulationOrigin(str, Enum):
    SCENARIO_SIMULATED = "scenario_simulated"
