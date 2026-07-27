"""Deterministic fallback policy for Leadership Brief generation."""

from __future__ import annotations

from app.domain.enums import RiskSeverity
from app.domain.leadership_brief_models import LeadershipDecision

READINESS_PROCEED_THRESHOLD = 75
READINESS_CONDITIONAL_THRESHOLD = 55
CONFIDENCE_LOW_THRESHOLD = 50
MAX_TOP_RISKS = 5
MAX_STAFFING_ACTIONS = 5
MAX_MITIGATION_ACTIONS = 5


def map_leadership_decision(
    *,
    readiness_score: int,
    confidence_score: int,
    has_high_risk: bool,
    has_critical_gap: bool,
    has_key_person_dependency: bool,
) -> LeadershipDecision:
    if has_high_risk and readiness_score < READINESS_CONDITIONAL_THRESHOLD:
        return LeadershipDecision.DO_NOT_PROCEED
    if has_high_risk or has_critical_gap:
        if (
            readiness_score >= READINESS_PROCEED_THRESHOLD
            and confidence_score >= CONFIDENCE_LOW_THRESHOLD
        ):
            return LeadershipDecision.PROCEED_WITH_CONDITIONS
        return LeadershipDecision.DEFER
    if (
        readiness_score >= READINESS_PROCEED_THRESHOLD
        and confidence_score >= CONFIDENCE_LOW_THRESHOLD
    ):
        if has_key_person_dependency:
            return LeadershipDecision.PROCEED_WITH_CONDITIONS
        return LeadershipDecision.PROCEED
    if readiness_score >= READINESS_CONDITIONAL_THRESHOLD:
        return LeadershipDecision.PROCEED_WITH_CONDITIONS
    return LeadershipDecision.DEFER


def severity_rank(severity: str) -> int:
    order = {
        RiskSeverity.HIGH.value: 0,
        RiskSeverity.MEDIUM.value: 1,
        RiskSeverity.LOW.value: 2,
    }
    return order.get(severity, 3)
