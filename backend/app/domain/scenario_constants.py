"""Versioned constants for Continuous Scenario Intelligence (Prompt 5)."""

from __future__ import annotations

SCENARIO_SCHEMA_VERSION = "scenario_assumptions_v1"
SCENARIO_FEATURE_OVERLAY_VERSION = "scenario_feature_overlay_v1"
SCENARIO_GRAPH_OVERLAY_VERSION = "scenario_graph_overlay_v1"
SOURCE_FINGERPRINT_VERSION = "scenario_source_fingerprint_v2"
RESULT_HASH_VERSION = "scenario_result_hash_v1"

SUPPORTED_HORIZONS: frozenset[int] = frozenset({30, 60, 90, 180})
DEFAULT_HORIZON_DAYS = 90

# Assumption / payload bounds
MAX_SCENARIO_CHANGES = 10
MAX_SUBJECT_IDS_PER_CHANGE = 50
MAX_ASSUMPTION_PAYLOAD_BYTES = 16_384
MAX_DESCRIPTION_CHARS = 2_000
MAX_NAME_CHARS = 200

# Graph overlay budgets
MAX_GRAPH_DEPTH = 10
MAX_GRAPH_NODES = 1_000
MAX_GRAPH_EDGES = 5_000
MAX_RETURNED_PATHS = 20
MAX_IMPACTS_PER_RESULT = 250
MAX_FACTORS = 8
MAX_DATA_QUALITY_WARNINGS = 32
MAX_APPLICABILITY_WARNINGS = 32
MAX_AFFECTED_NODE_IDS = 100
MAX_SUPPORTING_EDGE_IDS = 50
MAX_ASSUMPTION_IDS = 20
MAX_EXPLANATION_CHARS = 512
MAX_CHANGED_COMPONENTS = 32

# Watch / continuous evaluation bounds
MIN_WATCH_INTERVAL_MINUTES = 60
MAX_WATCHES_PER_EVALUATION_BATCH = 100
MAX_COMPARISON_RUNS = 20

# Scenario kind parameter bounds
MIN_REDUCTION_PERCENTAGE = 1
MAX_REDUCTION_PERCENTAGE = 100
MIN_DELAY_DAYS = 1
MAX_DELAY_DAYS = 180
MIN_DEADLINE_COMPRESSION_DAYS = 1
MAX_DEADLINE_COMPRESSION_DAYS = 90
MAX_UNAVAILABILITY_DAYS = 365
MAX_COMBINED_CHANGES = 10

# Feature overlay: only these features may change under documented rules.
OVERLAY_ALLOWED_FEATURES: frozenset[str] = frozenset(
    {
        "unavailable_owner_ratio",
        "active_engineer_owner_count",
        "ownership_redundancy",
        "single_person_dependency_count",
        "availability_blast_radius_count",
        "repository_ownership_concentration_count",
        "capability_ownership_concentration_count",
        "active_dependency_count",
        "dependency_depth",
        "cross_team_dependency_count",
        "active_dependency_cycle_indicator",
        "affected_critical_initiative_count",
        "finding_severity_critical_count",
        "finding_severity_high_count",
        "finding_severity_medium_count",
        "finding_severity_low_count",
        "team_availability_ratio",
        "critical_capability_gap_count",
        "critical_capability_owner_count",
        "capability_coverage",
        "incident_count_30d",
        "unresolved_incident_count",
        "planned_duration_days",
        "project_age_days_at_cutoff",
        "overdue_work_item_count",
        "blocked_work_item_count",
        "missing_owner_indicator",
    }
)

FORBIDDEN_ASSUMPTION_TOKENS: frozenset[str] = frozenset(
    {
        "email",
        "salary",
        "gender",
        "ethnicity",
        "religion",
        "health",
        "political",
        "password",
        "secret",
        "token",
        "ssn",
        "credential",
        "private_key",
        "authorization",
        "connection_string",
        "employee_rank",
        "performance_rating",
        "manager_sentiment",
        "private_message",
    }
)

# Responsible-use explanation templates (no causal / blame language).
SAFE_EXPLANATION_PREFIX = "This scenario"
FORBIDDEN_OUTPUT_PHRASES: frozenset[str] = frozenset(
    {
        "will cause failure",
        "is a risk",
        "definitely miss",
        "proves this intervention",
        "employee performance",
        "caused by the engineer",
    }
)
