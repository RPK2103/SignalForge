"""Thin orchestration layer between the v2 simulation API and domain services."""

from fastapi import HTTPException

from app.domain.evidence import deduplicate_team
from app.domain.policy import DEFAULT_POLICY_VERSION, get_policy
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.api_v2 import SimulationRequest, SimulationResponse
from app.services.identifiers import build_assessment_id, build_simulation_id
from app.services.simulation.exceptions import SimulationValidationError
from app.services.simulation.team_transformation import (
    TeamTransformationService,
    canonicalize_engineer_ids,
    normalize_engineer_id,
)
from app.services.team_simulation_service import TeamSimulationService


class SimulationOrchestrator:
    def __init__(
        self,
        catalog: CatalogRepository,
        simulation_service: TeamSimulationService | None = None,
        transformation_service: TeamTransformationService | None = None,
    ) -> None:
        self._catalog = catalog
        self._simulation_service = simulation_service or TeamSimulationService()
        self._transformation_service = transformation_service or TeamTransformationService()

    def simulate(self, request: SimulationRequest) -> SimulationResponse:
        if request.policy_version is not None:
            try:
                get_policy(request.policy_version)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        project = self._catalog.get_domain_project_by_id(request.project_id)
        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{request.project_id}' not found",
            )

        baseline_engineers = self._resolve_engineers(request.baseline_engineer_ids)
        baseline_ids = [engineer.id for engineer in baseline_engineers]
        canonical_baseline_ids = canonicalize_engineer_ids(request.baseline_engineer_ids)

        try:
            proposed_ids = self._transformation_service.compute_proposed_ids(
                baseline_ids,
                request.operation,
            )
        except SimulationValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

        proposed_engineers = self._resolve_engineers(proposed_ids)

        policy_version = request.policy_version or DEFAULT_POLICY_VERSION
        result = self._simulation_service.simulate(
            project=project,
            baseline_engineers=baseline_engineers,
            proposed_engineers=proposed_engineers,
            operation=request.operation,
            policy_version=request.policy_version,
        )

        unique_baseline, _ = deduplicate_team(baseline_engineers)
        unique_proposed, _ = deduplicate_team(proposed_engineers)

        simulation_id = build_simulation_id(
            project_id=request.project_id,
            baseline_engineer_ids=canonical_baseline_ids,
            operation=request.operation,
            proposed_engineer_ids=proposed_ids,
            policy_version=policy_version,
        )

        return SimulationResponse(
            simulation_id=simulation_id,
            project_id=project.id,
            operation=request.operation,
            baseline_team=unique_baseline,
            proposed_team=unique_proposed,
            baseline_assessment=self._wrap_assessment(
                request.project_id,
                unique_baseline,
                result.baseline_assessment,
                policy_version,
                request.policy_version,
            ),
            proposed_assessment=self._wrap_assessment(
                request.project_id,
                unique_proposed,
                result.proposed_assessment,
                policy_version,
                request.policy_version,
            ),
            readiness_score_delta=result.readiness_score_delta,
            confidence_delta=result.confidence_delta,
            risk_level_changes=result.risk_level_changes,
            capability_coverage_changes=result.capability_coverage_changes,
            newly_introduced_gaps=result.newly_introduced_gaps,
            resolved_gaps=result.resolved_gaps,
            key_person_dependency_changes=result.key_person_dependency_changes,
            decision_trace_delta=result.decision_trace_delta,
            recommended_mitigations=result.recommended_mitigations,
            policy_version=policy_version,
        )

    def _resolve_engineers(self, engineer_ids: list[str]):
        engineers = []
        for engineer_id in engineer_ids:
            normalized = normalize_engineer_id(engineer_id)
            engineer = self._catalog.get_domain_engineer_by_id(normalized)
            if engineer is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Engineer '{engineer_id}' not found",
                )
            engineers.append(engineer)
        return engineers

    def _wrap_assessment(
        self,
        project_id: str,
        team,
        assessment,
        policy_version: str,
        request_policy_version: str | None,
    ):
        from app.schemas.api_v2 import ReadinessAssessResponse

        return ReadinessAssessResponse(
            assessment_id=build_assessment_id(
                project_id,
                [engineer.id for engineer in team],
                policy_version,
            ),
            team=team,
            **assessment.model_dump(),
        )
