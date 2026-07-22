from fastapi import HTTPException

from app.adapters.legacy_mapper import (
    legacy_coverage_percentage,
    legacy_risk_level_from_coverage,
    legacy_success_probability,
    legacy_team_to_domain,
)
from app.repositories.mock_catalog_repository import MockCatalogRepository
from app.schemas.engineer import EngineerProfile
from app.schemas.project_fit import ProjectRequirements
from app.schemas.simulator import SimulateRequest, SimulateResponse
from app.services.fit_recommender import _score_fit
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService

_catalog = MockCatalogRepository()


def _recommended_team(
    project: ProjectRequirements,
    engineers: list[EngineerProfile],
) -> list[EngineerProfile]:
    scored = [
        (engineer, _score_fit(project.required_skills, engineer)[0])
        for engineer in engineers
    ]
    scored.sort(key=lambda item: (-item[1], item[0].name))
    return [engineer for engineer, _ in scored[:3]]


def _team_coverage_via_domain(
    project: ProjectRequirements,
    team: list[EngineerProfile],
) -> tuple[int, list[str]]:
    domain_project, domain_team = legacy_team_to_domain(project, team)
    coverage_results = CapabilityCoverageService().analyze(domain_project, domain_team)
    coverage_pct = legacy_coverage_percentage(coverage_results, len(project.required_skills))
    covered = [
        result.capability_name
        for result in coverage_results
        if result.level.value != "missing"
    ]
    return coverage_pct, covered


def _build_simulation_summary(
    removed_engineers: list[str],
    lost_capabilities: list[str],
    risk_after: str,
) -> str:
    names = ", ".join(removed_engineers)
    if not lost_capabilities:
        return (
            f"Removing {names} has minimal impact on capability coverage. "
            f"Delivery risk remains {risk_after.lower()}."
        )

    skills_text = ", ".join(lost_capabilities)
    return (
        f"Removing {names} significantly increases delivery risk because "
        f"{skills_text} capabilities are no longer fully covered."
    )


def simulate_staffing(request: SimulateRequest) -> SimulateResponse:
    project_name = request.project_name.strip()
    project = _catalog.get_legacy_project(project_name)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{request.project_name}' not found.",
        )

    if not request.remove_engineers:
        raise HTTPException(
            status_code=400,
            detail="remove_engineers must include at least one engineer name.",
        )

    resolved_removed: list[str] = []
    for name in request.remove_engineers:
        canonical = _catalog.resolve_engineer_name(name)
        if canonical is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown engineer '{name}'. Known engineers: "
                    f"{', '.join(_catalog.list_engineer_names())}."
                ),
            )
        if canonical not in resolved_removed:
            resolved_removed.append(canonical)

    original_team = _recommended_team(project, _catalog.list_legacy_engineers())
    original_names = [engineer.name for engineer in original_team]

    not_on_team = [name for name in resolved_removed if name not in original_names]
    if not_on_team:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Engineer(s) not on the recommended team for '{project.name}': "
                f"{', '.join(not_on_team)}. Team: {', '.join(original_names)}."
            ),
        )

    remaining_team = [
        engineer for engineer in original_team if engineer.name not in resolved_removed
    ]

    required_skills = project.required_skills
    coverage_before, covered_before = _team_coverage_via_domain(project, original_team)
    coverage_after, covered_after = _team_coverage_via_domain(project, remaining_team)

    lost_capabilities = [skill for skill in covered_before if skill not in covered_after]

    risk_before = legacy_risk_level_from_coverage(coverage_before)
    risk_after = legacy_risk_level_from_coverage(coverage_after)
    success_before = legacy_success_probability(coverage_before, risk_before)
    success_after = legacy_success_probability(coverage_after, risk_after)
    impact_score = max(0, success_before - success_after)

    summary = _build_simulation_summary(resolved_removed, lost_capabilities, risk_after)

    return SimulateResponse(
        project_name=project.name,
        removed_engineers=resolved_removed,
        original_team=original_names,
        remaining_team=[engineer.name for engineer in remaining_team],
        lost_capabilities=lost_capabilities,
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        risk_before=risk_before,
        risk_after=risk_after,
        success_probability_before=success_before,
        success_probability_after=success_after,
        impact_score=impact_score,
        simulation_summary=summary,
    )
