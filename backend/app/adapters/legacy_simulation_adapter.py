"""Legacy staffing simulator adapter over the v2 simulation engine."""

from fastapi import HTTPException

from app.adapters.legacy_mapper import (
    legacy_coverage_percentage,
    legacy_risk_level_from_coverage,
    legacy_success_probability,
)
from app.domain.simulation_models import CompareSimulationOperation
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.api_v2 import SimulationRequest
from app.schemas.engineer import EngineerProfile
from app.schemas.project_fit import ProjectRequirements
from app.schemas.simulator import SimulateRequest, SimulateResponse
from app.services.fit_recommender import _score_fit
from app.services.simulation_orchestrator import SimulationOrchestrator


def _recommended_team(
    project: ProjectRequirements,
    engineers: list[EngineerProfile],
) -> list[EngineerProfile]:
    scored = [
        (engineer, _score_fit(project.required_skills, engineer)[0]) for engineer in engineers
    ]
    scored.sort(key=lambda item: (-item[1], item[0].name))
    return [engineer for engineer, _ in scored[:3]]


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


class LegacySimulationAdapter:
    def __init__(
        self,
        catalog: CatalogRepository,
        orchestrator: SimulationOrchestrator | None = None,
    ) -> None:
        self._catalog = catalog
        self._orchestrator = orchestrator or SimulationOrchestrator(catalog=catalog)

    def simulate(self, request: SimulateRequest) -> SimulateResponse:
        project = self._catalog.get_legacy_project(request.project_name.strip())
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
            canonical = self._catalog.resolve_engineer_name(name)
            if canonical is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Unknown engineer '{name}'. Known engineers: "
                        f"{', '.join(self._catalog.list_engineer_names())}."
                    ),
                )
            if canonical not in resolved_removed:
                resolved_removed.append(canonical)

        original_team = _recommended_team(project, self._catalog.list_legacy_engineers())
        original_names = [engineer.name for engineer in original_team]
        original_ids = []
        for engineer in original_team:
            domain_engineer = self._catalog.get_domain_engineer_by_id(engineer.name.lower())
            if domain_engineer is not None:
                original_ids.append(domain_engineer.id)

        not_on_team = [name for name in resolved_removed if name not in original_names]
        if not_on_team:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Engineer(s) not on the recommended team for '{project.name}': "
                    f"{', '.join(not_on_team)}. Team: {', '.join(original_names)}."
                ),
            )

        remaining_ids = [
            engineer_id
            for engineer_id, name in zip(original_ids, original_names)
            if name not in resolved_removed
        ]
        remaining_names = [name for name in original_names if name not in resolved_removed]

        project_id = project.name.lower().replace(" ", "_")
        simulation = self._orchestrator.simulate(
            SimulationRequest(
                project_id=project_id,
                baseline_engineer_ids=original_ids,
                operation=CompareSimulationOperation(proposed_engineer_ids=remaining_ids),
            )
        )

        baseline_coverage = legacy_coverage_percentage(
            simulation.baseline_assessment.coverage_results,
            len(project.required_skills),
        )
        proposed_coverage = legacy_coverage_percentage(
            simulation.proposed_assessment.coverage_results,
            len(project.required_skills),
        )

        covered_before = [
            result.capability_name
            for result in simulation.baseline_assessment.coverage_results
            if result.level.value != "missing"
        ]
        covered_after = [
            result.capability_name
            for result in simulation.proposed_assessment.coverage_results
            if result.level.value != "missing"
        ]
        lost_capabilities = [skill for skill in covered_before if skill not in covered_after]

        risk_before = legacy_risk_level_from_coverage(baseline_coverage)
        risk_after = legacy_risk_level_from_coverage(proposed_coverage)
        success_before = legacy_success_probability(baseline_coverage, risk_before)
        success_after = legacy_success_probability(proposed_coverage, risk_after)
        impact_score = max(0, success_before - success_after)

        summary = _build_simulation_summary(resolved_removed, lost_capabilities, risk_after)

        return SimulateResponse(
            project_name=project.name,
            removed_engineers=resolved_removed,
            original_team=original_names,
            remaining_team=remaining_names,
            lost_capabilities=lost_capabilities,
            coverage_before=baseline_coverage,
            coverage_after=proposed_coverage,
            risk_before=risk_before,
            risk_after=risk_after,
            success_probability_before=success_before,
            success_probability_after=success_after,
            impact_score=impact_score,
            simulation_summary=summary,
        )
