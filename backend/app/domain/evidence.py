"""Evidence and proficiency helpers shared across intelligence services."""

from app.domain.capability_registry import get_capability
from app.domain.enums import CoverageLevel, EvidenceSource
from app.domain.models import EngineerCapability, EngineerProfile
from app.domain.policy import get_policy


def classify_coverage_level(team_proficiency: int, covering_count: int) -> CoverageLevel:
    if covering_count == 0 or team_proficiency == 0:
        return CoverageLevel.MISSING
    policy = get_policy()
    if team_proficiency <= policy.WEAK_PROFICIENCY_MAX:
        return CoverageLevel.WEAK
    if team_proficiency >= policy.STRONG_PROFICIENCY_MIN:
        return CoverageLevel.STRONG
    return CoverageLevel.ADEQUATE


def compute_engineer_proficiency(
    capability_id: str,
    evidence_sources: list[EvidenceSource],
    experience_years: float,
) -> int:
    policy = get_policy()
    has_skill = EvidenceSource.SKILLS in evidence_sources
    has_cert = EvidenceSource.CERTIFICATIONS in evidence_sources
    has_project = EvidenceSource.PROJECTS in evidence_sources

    if has_skill and has_cert and has_project:
        base = policy.PROFICIENCY_SKILL_CERT_PROJECT
    elif has_skill and has_cert:
        base = policy.PROFICIENCY_SKILL_CERT
    elif has_skill and has_project:
        base = policy.PROFICIENCY_SKILL_PROJECT
    elif has_skill:
        base = policy.PROFICIENCY_SKILL_ONLY
    else:
        base = 0

    exp_bonus = min(
        policy.PROFICIENCY_EXPERIENCE_BONUS_CAP,
        int(experience_years * policy.PROFICIENCY_EXPERIENCE_BONUS_PER_YEAR),
    )
    return min(100, base + exp_bonus)


def team_proficiency_for_capability(
    team: list[EngineerProfile],
    capability_id: str,
) -> tuple[int, list[str]]:
    """Return max proficiency and list of covering engineer ids."""
    covering_ids: list[str] = []
    max_proficiency = 0

    for engineer in team:
        for cap in engineer.capabilities:
            if cap.capability_id == capability_id:
                covering_ids.append(engineer.id)
                max_proficiency = max(max_proficiency, cap.proficiency)
                break

    return max_proficiency, covering_ids


def deduplicate_team(team: list[EngineerProfile]) -> tuple[list[EngineerProfile], list[str]]:
    """Remove duplicate engineers by id, preserving first occurrence."""
    seen: set[str] = set()
    unique: list[EngineerProfile] = []
    duplicate_ids: list[str] = []

    for engineer in team:
        if engineer.id in seen:
            duplicate_ids.append(engineer.id)
            continue
        seen.add(engineer.id)
        unique.append(engineer)

    return unique, duplicate_ids


def coverage_percentage(coverage_results: list) -> int:
    if not coverage_results:
        return 100
    weighted_total = sum(result.weight for result in coverage_results)
    if weighted_total == 0:
        return 100
    earned = sum(
        result.weight * get_policy().LEVEL_MULTIPLIERS[result.level.value]
        for result in coverage_results
    )
    return round(earned / weighted_total * 100)


def capability_display_name(capability_id: str) -> str:
    definition = get_capability(capability_id)
    return definition.name if definition else capability_id.replace("_", " ").title()
