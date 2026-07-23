from enum import Enum


class CapabilityCategory(str, Enum):
    BACKEND = "backend"
    CLOUD = "cloud"
    AI = "ai"
    DATA = "data"
    DEVOPS = "devops"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    DELIVERY_EXECUTION = "delivery_execution"


class CoverageLevel(str, Enum):
    MISSING = "missing"
    WEAK = "weak"
    ADEQUATE = "adequate"
    STRONG = "strong"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskFindingType(str, Enum):
    MISSING_CRITICAL_CAPABILITY = "missing_critical_capability"
    WEAK_CAPABILITY = "weak_capability"
    KEY_PERSON_DEPENDENCY = "key_person_dependency"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"
    DUPLICATE_TEAM_MEMBER = "duplicate_team_member"
    EMPTY_TEAM = "empty_team"


class ReadinessDimension(str, Enum):
    CAPABILITY_COVERAGE = "capability_coverage"
    SKILL_DEPTH = "skill_depth"
    TEAM_BALANCE = "team_balance"
    DELIVERY_RISK = "delivery_risk"
    EVIDENCE_QUALITY = "evidence_quality"


class EvidenceSource(str, Enum):
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    PROJECTS = "projects"
    EXPERIENCE = "experience"


class SimulationOperationType(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    COMPARE = "compare"


class SimulationChangeType(str, Enum):
    INTRODUCED = "introduced"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    DEESCALATED = "deescalated"
    IMPROVED = "improved"
    DEGRADED = "degraded"
    MODIFIED = "modified"


class MitigationType(str, Enum):
    ADD_CAPABILITY_COVERAGE = "add_capability_coverage"
    STRENGTHEN_CAPABILITY_COVERAGE = "strengthen_capability_coverage"
    ESTABLISH_SECONDARY_OWNER = "establish_secondary_owner"
    PRESERVE_CRITICAL_ENGINEER = "preserve_critical_engineer"
    IMPROVE_ENGINEER_EVIDENCE = "improve_engineer_evidence"
    REASSESS_PROJECT_SCOPE = "reassess_project_scope"
    REPLACE_WITH_STRONGER_MATCH = "replace_with_stronger_match"


class MitigationPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HumanReviewState(str, Enum):
    ACCEPTED = "accepted"
    OVERRIDDEN = "overridden"
    NEEDS_MORE_DATA = "needs_more_data"


class AuditEventType(str, Enum):
    ASSESSMENT_CREATED = "assessment_created"
    SIMULATION_CREATED = "simulation_created"
    HUMAN_REVIEW_CREATED = "human_review_created"
    LEADERSHIP_BRIEF_CREATED = "leadership_brief_created"


class AuditAggregateType(str, Enum):
    ASSESSMENT = "assessment"
    SIMULATION = "simulation"
    HUMAN_REVIEW = "human_review"


class ScenarioType(str, Enum):
    READINESS = "readiness"
    SIMULATION = "simulation"
