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
