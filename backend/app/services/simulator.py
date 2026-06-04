from fastapi import HTTPException

from app.data.mock_catalog import MOCK_ENGINEERS, MOCK_PROJECTS
from app.schemas.engineer import EngineerProfile
from app.schemas.project_fit import ProjectRequirements
from app.schemas.simulator import SimulateRequest, SimulateResponse
from app.services.fit_recommender import _is_skill_matched, _score_fit


def _resolve_engineer_name(name: str) -> str | None:
    normalized = name.strip().lower()
    for canonical in MOCK_ENGINEERS:
        if canonical.lower() == normalized:
            return canonical
    return None


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


def _team_coverage(
    required_skills: list[str],
    team: list[EngineerProfile],
) -> tuple[int, list[str]]:
    if not required_skills:
        return 100, []

    covered = [
        skill
        for skill in required_skills
        if any(_is_skill_matched(skill, engineer) for engineer in team)
    ]
    coverage = round(len(covered) / len(required_skills) * 100)
    return coverage, covered


def _risk_level(coverage: int) -> str:
    """Map capability coverage to delivery risk (used for risk_before and risk_after).

    Thresholds:
    - coverage >= 80 → Low
    - coverage >= 70 and < 80 → Medium
    - coverage < 70 → High
    """
    if coverage >= 80:
        return "Low"
    if coverage >= 70:
        return "Medium"
    return "High"


def _success_probability(coverage: int, risk_level: str) -> int:
    penalties = {"Low": 0, "Medium": 15, "High": 30}
    penalty = penalties[risk_level]
    return max(0, min(100, coverage - penalty))


def _skills_provided_by(
    engineers: list[EngineerProfile],
    required_skills: list[str],
) -> list[str]:
    return [
        skill
        for skill in required_skills
        if any(_is_skill_matched(skill, engineer) for engineer in engineers)
    ]


def _build_simulation_summary(
    removed_engineers: list[str],
    lost_capabilities: list[str],
    risk_after: str,
) -> str:
    names = ", ".join(removed_engineers)
    if not lost_capabilities:
        if len(removed_engineers) == 1:
            return (
                f"Removing {names} has minimal impact on capability coverage. "
                f"Delivery risk remains {risk_after.lower()}."
            )
        return (
            f"Removing {names} has minimal impact on capability coverage. "
            f"Delivery risk remains {risk_after.lower()}."
        )

    skills_text = ", ".join(lost_capabilities)
    if len(removed_engineers) == 1:
        return (
            f"Removing {names} significantly increases delivery risk because "
            f"{skills_text} capabilities are no longer fully covered."
        )
    return (
        f"Removing {names} significantly increases delivery risk because "
        f"{skills_text} capabilities are no longer fully covered."
    )


def simulate_staffing(request: SimulateRequest) -> SimulateResponse:
    project_name = request.project_name.strip()
    project = MOCK_PROJECTS.get(project_name)
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
        canonical = _resolve_engineer_name(name)
        if canonical is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown engineer '{name}'. Known engineers: {', '.join(sorted(MOCK_ENGINEERS))}.",
            )
        if canonical not in resolved_removed:
            resolved_removed.append(canonical)

    original_team = _recommended_team(project, list(MOCK_ENGINEERS.values()))
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
    coverage_before, covered_before = _team_coverage(required_skills, original_team)
    coverage_after, covered_after = _team_coverage(required_skills, remaining_team)

    lost_capabilities = [skill for skill in covered_before if skill not in covered_after]

    risk_before = _risk_level(coverage_before)
    risk_after = _risk_level(coverage_after)
    success_before = _success_probability(coverage_before, risk_before)
    success_after = _success_probability(coverage_after, risk_after)
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
