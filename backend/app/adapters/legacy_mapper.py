"""Translate legacy MVP schemas to Phase 2 domain models and back."""

from app.domain.capability_registry import resolve_capability_id
from app.domain.enums import EvidenceSource
from app.domain.evidence import compute_engineer_proficiency
from app.domain.models import (
    EngineerCapability,
    EngineerProfile,
    ProjectProfile,
    ProjectRequirement,
    TeamComposition,
)
from app.domain.policy import get_policy
from app.schemas.engineer import EngineerProfile as LegacyEngineerProfile
from app.schemas.project_fit import ProjectRequirements


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _legacy_skill_sources(required_label: str, profile: LegacyEngineerProfile) -> list[EvidenceSource]:
    sources: list[EvidenceSource] = []
    target = required_label.lower()

    if any(skill.lower() == target for skill in profile.skills):
        sources.append(EvidenceSource.SKILLS)
    if any(target in cert.lower() for cert in profile.certifications):
        sources.append(EvidenceSource.CERTIFICATIONS)
    if any(target in project.lower() for project in profile.projects):
        sources.append(EvidenceSource.PROJECTS)

    return sources


def legacy_engineer_to_domain(profile: LegacyEngineerProfile) -> EngineerProfile:
    capabilities: list[EngineerCapability] = []
    seen_ids: set[str] = set()

    for skill in profile.skills:
        cap_id = resolve_capability_id(skill)
        if cap_id is None or cap_id in seen_ids:
            continue
        seen_ids.add(cap_id)
        sources = _legacy_skill_sources(skill, profile)
        if EvidenceSource.EXPERIENCE not in sources and profile.experience >= 2:
            sources = list(sources)
        proficiency = compute_engineer_proficiency(cap_id, sources, float(profile.experience))
        capabilities.append(
            EngineerCapability(
                capability_id=cap_id,
                proficiency=proficiency,
                evidence_sources=sources,
            )
        )

    for cert in profile.certifications:
        cap_id = resolve_capability_id(cert)
        if cap_id is None or cap_id in seen_ids:
            continue
        seen_ids.add(cap_id)
        sources = _legacy_skill_sources(cert, profile)
        proficiency = compute_engineer_proficiency(cap_id, sources, float(profile.experience))
        capabilities.append(
            EngineerCapability(
                capability_id=cap_id,
                proficiency=proficiency,
                evidence_sources=sources,
            )
        )

    return EngineerProfile(
        id=_slugify(profile.name),
        name=profile.name,
        experience_years=float(profile.experience),
        capabilities=capabilities,
        has_certifications=bool(profile.certifications),
        has_project_history=bool(profile.projects),
    )


def legacy_engineers_to_domain(profiles: list[LegacyEngineerProfile]) -> list[EngineerProfile]:
    return [legacy_engineer_to_domain(profile) for profile in profiles]


def legacy_project_to_domain(
    project: ProjectRequirements,
    critical_skills: list[str] | None = None,
) -> ProjectProfile:
    critical = {skill.lower() for skill in (critical_skills or [])}
    requirements: list[ProjectRequirement] = []

    for skill in project.required_skills:
        cap_id = resolve_capability_id(skill)
        if cap_id is None:
            cap_id = _slugify(skill)
        requirements.append(
            ProjectRequirement(
                capability_id=cap_id,
                weight=1.0,
                critical=skill.lower() in critical or len(project.required_skills) <= 3,
            )
        )

    return ProjectProfile(
        id=_slugify(project.name),
        name=project.name,
        requirements=requirements,
    )


def legacy_team_to_domain(
    project: ProjectRequirements,
    engineers: list[LegacyEngineerProfile],
    critical_skills: list[str] | None = None,
) -> tuple[ProjectProfile, TeamComposition]:
    return (
        legacy_project_to_domain(project, critical_skills),
        TeamComposition(engineers=legacy_engineers_to_domain(engineers)),
    )


def domain_coverage_to_legacy_skill_names(coverage_results) -> tuple[list[str], list[str]]:
    """Map domain coverage results back to legacy skill label lists."""
    covered: list[str] = []
    missing: list[str] = []
    for result in coverage_results:
        if result.level.value == "missing":
            missing.append(result.capability_name)
        else:
            covered.append(result.capability_name)
    return covered, missing


def legacy_coverage_percentage(coverage_results, required_count: int) -> int:
    """Boolean coverage percentage compatible with legacy MVP endpoints."""
    if required_count == 0:
        return 100
    covered = sum(1 for result in coverage_results if result.level.value != "missing")
    return round(covered / required_count * 100)


def legacy_risk_level_from_coverage(coverage_pct: int) -> str:
    policy = get_policy()
    if coverage_pct >= policy.RISK_COVERAGE_LOW_MIN:
        return "Low"
    if coverage_pct >= policy.RISK_COVERAGE_MEDIUM_MIN:
        return "Medium"
    return "High"


def legacy_success_probability(coverage_pct: int, risk_level: str) -> int:
    policy = get_policy()
    penalty = policy.SUCCESS_RISK_PENALTIES[risk_level]
    return max(0, min(100, coverage_pct - penalty))


def legacy_delivery_risk_score(coverage_pct: int) -> int:
    policy = get_policy()
    level = legacy_risk_level_from_coverage(coverage_pct)
    return policy.DELIVERY_RISK_SCORES[level]


def legacy_confidence_label_from_score(score: int) -> str:
    policy = get_policy()
    if score >= 90:
        return "High"
    if score >= 70:
        return "Medium"
    return "Low"


def legacy_confidence_label_from_probability(probability: int) -> str:
    return legacy_confidence_label_from_score(probability)
