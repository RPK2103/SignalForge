"""Version 1 readiness scoring policy — explicit, deterministic, testable rules."""

POLICY_VERSION = "v1"

# Coverage classification thresholds (team proficiency 0-100)
WEAK_PROFICIENCY_MAX = 39
ADEQUATE_PROFICIENCY_MIN = 40
ADEQUATE_PROFICIENCY_MAX = 69
STRONG_PROFICIENCY_MIN = 70

# Contribution multipliers per coverage level (applied to requirement weight)
LEVEL_MULTIPLIERS: dict[str, float] = {
    "missing": 0.0,
    "weak": 0.4,
    "adequate": 0.7,
    "strong": 1.0,
}

# Legacy-compatible delivery risk thresholds (capability coverage %)
RISK_COVERAGE_LOW_MIN = 80
RISK_COVERAGE_MEDIUM_MIN = 70

# Legacy-compatible success probability weights
SUCCESS_COVERAGE_WEIGHT = 0.5
SUCCESS_TEAM_QUALITY_WEIGHT = 0.3
SUCCESS_RISK_INVERSE_WEIGHT = 0.2

# Numeric delivery risk scores by risk level label
DELIVERY_RISK_SCORES = {
    "Low": 10,
    "Medium": 45,
    "High": 75,
}

# Success probability risk penalties (legacy simulator)
SUCCESS_RISK_PENALTIES = {
    "Low": 0,
    "Medium": 15,
    "High": 30,
}

# Confidence scoring — separate from readiness
CONFIDENCE_BASE = 100
CONFIDENCE_NO_CERTIFICATIONS_PENALTY = 8
CONFIDENCE_NO_PROJECTS_PENALTY = 8
CONFIDENCE_INCOMPLETE_EVIDENCE_PENALTY = 12
CONFIDENCE_KEY_PERSON_PENALTY = 15
CONFIDENCE_MISSING_CRITICAL_PENALTY = 20
CONFIDENCE_WEAK_CRITICAL_PENALTY = 10
CONFIDENCE_EMPTY_TEAM_PENALTY = 40
CONFIDENCE_DUPLICATE_MEMBER_PENALTY = 10

CONFIDENCE_LEVEL_HIGH_MIN = 80
CONFIDENCE_LEVEL_MEDIUM_MIN = 50

# Readiness dimension weights (must sum to 1.0)
DIMENSION_WEIGHTS: dict[str, float] = {
    "capability_coverage": 0.45,
    "skill_depth": 0.20,
    "team_balance": 0.15,
    "delivery_risk": 0.10,
    "evidence_quality": 0.10,
}

# Proficiency scoring from evidence sources
PROFICIENCY_SKILL_ONLY = 55
PROFICIENCY_SKILL_CERT = 75
PROFICIENCY_SKILL_PROJECT = 65
PROFICIENCY_SKILL_CERT_PROJECT = 85
PROFICIENCY_EXPERIENCE_BONUS_PER_YEAR = 2
PROFICIENCY_EXPERIENCE_BONUS_CAP = 15

# Engineer evidence thresholds
MIN_EXPERIENCE_YEARS_FOR_ADEQUATE = 2
