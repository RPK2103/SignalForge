"""Prove simulation nested assessments match direct readiness assessments."""

from app.domain.simulation_models import RemoveSimulationOperation
from app.repositories.mock_catalog_repository import MockCatalogRepository
from app.schemas.api_v2 import ReadinessAssessRequest, SimulationRequest
from app.services.readiness_orchestrator import ReadinessOrchestrator
from app.services.simulation_orchestrator import SimulationOrchestrator


CATALOG = MockCatalogRepository()
READINESS = ReadinessOrchestrator(catalog=CATALOG)
SIMULATION = SimulationOrchestrator(catalog=CATALOG)

PROJECT_ID = "azure_ai_migration"
BASELINE_IDS = ["kavi", "vikram"]


def _domain_fields(response) -> dict:
    """Extract deterministic domain fields excluding API envelope metadata."""
    data = response.model_dump()
    data.pop("assessment_id", None)
    data.pop("team", None)
    return data


class TestSimulationAssessmentEquivalence:
    def test_baseline_assessment_matches_direct_readiness(self):
        simulation = SIMULATION.simulate(
            SimulationRequest(
                project_id=PROJECT_ID,
                baseline_engineer_ids=BASELINE_IDS,
                operation=RemoveSimulationOperation(engineer_id="kavi"),
            )
        )
        direct_baseline = READINESS.assess(
            ReadinessAssessRequest(
                project_id=PROJECT_ID,
                engineer_ids=BASELINE_IDS,
            )
        )
        assert _domain_fields(simulation.baseline_assessment) == _domain_fields(
            direct_baseline
        )
        assert (
            simulation.baseline_assessment.assessment_id
            == direct_baseline.assessment_id
        )

    def test_proposed_assessment_matches_direct_readiness(self):
        simulation = SIMULATION.simulate(
            SimulationRequest(
                project_id=PROJECT_ID,
                baseline_engineer_ids=BASELINE_IDS,
                operation=RemoveSimulationOperation(engineer_id="kavi"),
            )
        )
        direct_proposed = READINESS.assess(
            ReadinessAssessRequest(
                project_id=PROJECT_ID,
                engineer_ids=["vikram"],
            )
        )
        assert _domain_fields(simulation.proposed_assessment) == _domain_fields(
            direct_proposed
        )
        assert (
            simulation.proposed_assessment.assessment_id
            == direct_proposed.assessment_id
        )
