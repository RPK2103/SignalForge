"""Public team simulation service built on the readiness assessment domain."""

from app.domain.evidence import deduplicate_team
from app.domain.models import ProjectProfile, ReadinessAssessmentRequest, TeamComposition
from app.domain.policy import DEFAULT_POLICY_VERSION
from app.domain.simulation_models import SimulationOperation, SimulationResult, SimulationTeamSnapshot
from app.services.intelligence.readiness_assessment_service import ReadinessAssessmentService
from app.services.simulation.mitigation_service import MitigationService
from app.services.simulation.simulation_delta_service import SimulationDeltaService


class TeamSimulationService:
    def __init__(
        self,
        assessment_service: ReadinessAssessmentService | None = None,
        delta_service: SimulationDeltaService | None = None,
        mitigation_service: MitigationService | None = None,
    ) -> None:
        self._assessment_service = assessment_service or ReadinessAssessmentService()
        self._delta_service = delta_service or SimulationDeltaService()
        self._mitigation_service = mitigation_service or MitigationService()

    def simulate(
        self,
        project: ProjectProfile,
        baseline_engineers: list,
        proposed_engineers: list,
        operation: SimulationOperation,
        policy_version: str | None = None,
    ) -> SimulationResult:
        resolved_policy = policy_version or DEFAULT_POLICY_VERSION

        baseline_copy = list(baseline_engineers)
        proposed_copy = list(proposed_engineers)

        baseline_unique, _ = deduplicate_team(baseline_copy)
        proposed_unique, _ = deduplicate_team(proposed_copy)

        baseline_assessment = self._assessment_service.assess(
            ReadinessAssessmentRequest(
                project=project,
                team=TeamComposition(engineers=baseline_unique),
            ),
            policy_version=policy_version,
        )
        proposed_assessment = self._assessment_service.assess(
            ReadinessAssessmentRequest(
                project=project,
                team=TeamComposition(engineers=proposed_unique),
            ),
            policy_version=policy_version,
        )

        deltas = self._delta_service.compare(baseline_assessment, proposed_assessment)
        result = SimulationResult(
            project_id=project.id,
            operation=operation,
            baseline_team=SimulationTeamSnapshot(
                engineer_ids=[engineer.id for engineer in baseline_unique],
                engineers=baseline_unique,
            ),
            proposed_team=SimulationTeamSnapshot(
                engineer_ids=[engineer.id for engineer in proposed_unique],
                engineers=proposed_unique,
            ),
            baseline_assessment=baseline_assessment,
            proposed_assessment=proposed_assessment,
            policy_version=resolved_policy,
            **deltas,
        )
        result.recommended_mitigations = self._mitigation_service.recommend(result)
        return result
