from fastapi import HTTPException

from app.adapters.legacy_mapper import (
    legacy_confidence_label_from_probability,
    legacy_coverage_percentage,
    legacy_delivery_risk_score,
    legacy_risk_level_from_coverage,
    legacy_team_to_domain,
)
from app.repositories.mock_catalog_repository import MockCatalogRepository
from app.schemas.predictor import SuccessPredictionRequest, SuccessPredictionResponse
from app.services.fit_recommender import _score_fit
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService
from app.services.simulator import _recommended_team

_catalog = MockCatalogRepository()


def _team_quality_score(required_skills: list[str], team: list) -> int:
    if not team:
        return 0
    fit_scores = [_score_fit(required_skills, engineer)[0] for engineer in team]
    return round(sum(fit_scores) / len(fit_scores))


def _outlook_for_probability(probability: int) -> str:
    if probability >= 90:
        return "Likely Success"
    if probability >= 70:
        return "Moderate Risk"
    return "High Risk"


def _generate_reasoning(
    coverage: int,
    missing_skills: list[str],
    risk_level: str,
    team_quality: int,
    covered_skills: list[str],
) -> list[str]:
    reasons: list[str] = []

    if coverage >= 100 or not missing_skills:
        reasons.append("Full capability coverage")
    elif coverage >= 80:
        reasons.append("Strong capability coverage")
    else:
        reasons.append("Missing critical capabilities")

    if risk_level == "Low":
        reasons.append("Low delivery risk")
    elif risk_level == "Medium":
        reasons.append("Moderate delivery risk")
    else:
        reasons.append("Elevated delivery risk")

    if "Generative AI" in covered_skills:
        reasons.append("Strong AI capability")
    elif "Azure" in covered_skills:
        reasons.append("Strong Azure expertise")
    elif covered_skills:
        reasons.append(f"Strong {covered_skills[0]} expertise")

    if team_quality >= 75:
        reasons.append("Highly qualified team")
    elif team_quality >= 60:
        reasons.append("Balanced engineering team")
    else:
        reasons.append("Team capability gaps remain")

    return reasons[:4]


def _build_summary(
    success_probability: int,
    coverage: int,
    risk_level: str,
    team_quality: int,
) -> str:
    if success_probability >= 90:
        return (
            "This project has a high likelihood of successful execution due to strong "
            "skill coverage, low delivery risk, and a well-balanced engineering team."
        )
    if success_probability >= 70:
        coverage_note = (
            "solid capability coverage"
            if coverage >= 80
            else "partial capability coverage"
        )
        return (
            f"This project has a moderate delivery outlook with {coverage_note}, "
            f"{risk_level.lower()} delivery risk, and a team quality score of "
            f"{team_quality}/100."
        )
    return (
        f"This project faces elevated delivery risk due to capability gaps, "
        f"{risk_level.lower()} risk exposure, and limited team readiness "
        f"({team_quality}/100 team quality)."
    )


def predict_success(request: SuccessPredictionRequest) -> SuccessPredictionResponse:
    project_name = request.project_name.strip()
    project = _catalog.get_legacy_project(project_name)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{request.project_name}' not found.",
        )

    team = _recommended_team(project, _catalog.list_legacy_engineers())
    required_skills = project.required_skills

    domain_project, domain_team = legacy_team_to_domain(project, team)
    coverage_results = CapabilityCoverageService().analyze(domain_project, domain_team)
    coverage = legacy_coverage_percentage(coverage_results, len(required_skills))
    covered_skills = [
        result.capability_name
        for result in coverage_results
        if result.level.value != "missing"
    ]
    missing_skills = [
        result.capability_name
        for result in coverage_results
        if result.level.value == "missing"
    ]

    risk_level = legacy_risk_level_from_coverage(coverage)
    risk_score = legacy_delivery_risk_score(coverage)
    team_quality = _team_quality_score(required_skills, team)

    raw_probability = (
        0.5 * coverage + 0.3 * team_quality + 0.2 * (100 - risk_score)
    )
    success_probability = max(0, min(100, round(raw_probability)))

    reasoning = _generate_reasoning(
        coverage=coverage,
        missing_skills=missing_skills,
        risk_level=risk_level,
        team_quality=team_quality,
        covered_skills=covered_skills,
    )
    summary = _build_summary(success_probability, coverage, risk_level, team_quality)

    return SuccessPredictionResponse(
        project_name=project.name,
        success_probability=success_probability,
        confidence=legacy_confidence_label_from_probability(success_probability),
        delivery_outlook=_outlook_for_probability(success_probability),
        reasoning=reasoning,
        summary=summary,
    )
