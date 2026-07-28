"""Delivery Graph enums (Phase 3 Prompt 3).

Bounded, deterministic identifiers. Graph confidence is rule-based evidence
support — not Phase 2 assessment confidence and not statistically calibrated.
"""

from enum import Enum


class GraphNodeType(str, Enum):
    ORGANIZATION = "organization"
    BUSINESS_UNIT = "business_unit"
    DEPARTMENT = "department"
    TEAM = "team"
    ENGINEER = "engineer"
    INITIATIVE = "initiative"
    PROJECT = "project"
    CAPABILITY = "capability"
    SKILL = "skill"
    REPOSITORY = "repository"
    PULL_REQUEST = "pull_request"
    WORK_ITEM = "work_item"
    SPRINT = "sprint"
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"


class GraphEdgeType(str, Enum):
    MEMBER_OF = "member_of"
    OWNS = "owns"
    CONTRIBUTES_TO = "contributes_to"
    REVIEWS = "reviews"
    DEPENDS_ON = "depends_on"
    SUPPORTS = "supports"
    BLOCKS = "blocks"
    REQUIRES = "requires"
    DEPLOYED_BY = "deployed_by"
    RESPONDS_TO = "responds_to"
    TRANSFERS_KNOWLEDGE_TO = "transfers_knowledge_to"


class GraphEdgeOrigin(str, Enum):
    CATALOG = "catalog"
    MANUAL = "manual"
    CONNECTOR = "connector"
    DERIVED = "derived"


class GraphProjectionMode(str, Enum):
    FULL_REBUILD = "full_rebuild"
    INCREMENTAL = "incremental"
    SUBJECT_REFRESH = "subject_refresh"


class GraphProjectionRunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class GraphAnalysisRunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class GraphFindingType(str, Enum):
    SINGLE_PERSON_DEPENDENCY = "single_person_dependency"
    REPOSITORY_OWNERSHIP_CONCENTRATION = "repository_ownership_concentration"
    CAPABILITY_OWNERSHIP_CONCENTRATION = "capability_ownership_concentration"
    CROSS_TEAM_DEPENDENCY = "cross_team_dependency"
    DERIVED_UNMODELED_DEPENDENCY = "derived_unmodeled_dependency"
    DEPENDENCY_CYCLE = "dependency_cycle"
    AVAILABILITY_BLAST_RADIUS = "availability_blast_radius"
    KNOWLEDGE_CONCENTRATION = "knowledge_concentration"


class GraphFindingStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class GraphFindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class GraphDataQualityWarning(str, Enum):
    STALE_EVIDENCE = "stale_evidence"
    MISSING_OWNER = "missing_owner"
    MISSING_TEAM_MAPPING = "missing_team_mapping"
    INCOMPLETE_CAPABILITY_MAPPING = "incomplete_capability_mapping"
    UNRESOLVED_ACTOR_IDENTITY = "unresolved_actor_identity"
    NO_EXPLICIT_DEPENDENCY_RECORD = "no_explicit_dependency_record"
    INSUFFICIENT_HISTORY = "insufficient_history"


# Versioned projection / analysis / confidence rule identifiers.
GRAPH_PROJECTION_VERSION = "1"
GRAPH_ANALYSIS_VERSION = "1"
GRAPH_CONFIDENCE_RULE_VERSION = "1"
GRAPH_DERIVATION_VERSION = "1"
