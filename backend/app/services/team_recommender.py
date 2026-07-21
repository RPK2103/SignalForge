from app.adapters.legacy_mapper import (
    domain_coverage_to_legacy_skill_names,
    legacy_team_to_domain,
)
from app.schemas.engineer import EngineerProfile
from app.schemas.team import (
    RecommendedEngineer,
    TeamRecommendationRequest,
    TeamRecommendationResponse,
)
from app.services.fit_recommender import _score_fit
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService


def _has_skill(skills: list[str], target: str) -> bool:
    target_lower = target.lower()
    return any(skill.lower() == target_lower for skill in skills)


def _assign_role(engineer: EngineerProfile) -> str:
    skills = engineer.skills

    has_azure = _has_skill(skills, "Azure")
    has_python = _has_skill(skills, "Python")
    has_gen_ai = _has_skill(skills, "Generative AI")
    has_frontend = any(_has_skill(skills, skill) for skill in ("React", "UI", "Figma"))

    if has_azure and has_python and has_gen_ai and engineer.experience >= 5:
        return "Lead AI Engineer"
    if has_azure and has_python and has_gen_ai:
        return "AI Engineer"
    if has_azure and has_python:
        return "Cloud Engineer"
    if has_gen_ai:
        return "AI Specialist"
    if has_frontend:
        return "Frontend Engineer"
    return "Software Engineer"


def _build_summary(
    required_skills: list[str],
    team_coverage: list[str],
    missing_coverage: list[str],
) -> str:
    if not required_skills:
        return "No specific skill requirements defined. Team selected by individual fit scores."

    if not missing_coverage:
        return "Recommended team covers all required project capabilities."

    missing_text = ", ".join(missing_coverage)
    return (
        f"Recommended team covers {len(team_coverage)} of {len(required_skills)} "
        f"required skills. Missing coverage: {missing_text}."
    )


def recommend_team(request: TeamRecommendationRequest) -> TeamRecommendationResponse:
    project = request.project
    required_skills = project.required_skills

    scored: list[tuple] = []
    for engineer in request.engineers:
        fit_score, matched, _ = _score_fit(required_skills, engineer)
        scored.append((engineer, fit_score, matched))

    scored.sort(key=lambda item: (-item[1], item[0].name))

    top_engineers = scored[:3]
    recommended_team = [
        RecommendedEngineer(
            name=engineer.name,
            fit_score=fit_score,
            role=_assign_role(engineer),
        )
        for engineer, fit_score, _ in top_engineers
    ]

    domain_project, domain_team = legacy_team_to_domain(
        project,
        [engineer for engineer, _, _ in top_engineers],
    )
    coverage_results = CapabilityCoverageService().analyze(domain_project, domain_team)
    team_coverage, missing_coverage = domain_coverage_to_legacy_skill_names(coverage_results)

    summary = _build_summary(required_skills, team_coverage, missing_coverage)

    return TeamRecommendationResponse(
        project_name=project.name,
        recommended_team=recommended_team,
        team_coverage=team_coverage,
        missing_coverage=missing_coverage,
        summary=summary,
    )
