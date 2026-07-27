"""SQL catalog repository parity with mock catalog."""

from app.domain.simulation_models import RemoveSimulationOperation
from app.schemas.api_v2 import ReadinessAssessRequest, SimulationRequest
from app.services.readiness_orchestrator import ReadinessOrchestrator
from app.services.simulation_orchestrator import SimulationOrchestrator


def test_engineer_list_parity(db_session, mock_catalog):
    from app.db.repositories.sql_repositories import SqlCatalogRepository

    sql = SqlCatalogRepository(db_session)
    mock_engineers = {e.id for e in mock_catalog.get_domain_engineers()}
    sql_engineers = {e.id for e in sql.get_domain_engineers()}
    assert mock_engineers == sql_engineers


def test_readiness_parity(db_session, mock_catalog):
    from app.db.repositories.sql_repositories import SqlCatalogRepository

    sql = SqlCatalogRepository(db_session)
    request = ReadinessAssessRequest(
        project_id="azure_ai_migration",
        engineer_ids=["kavi", "vikram"],
    )
    mock_result = ReadinessOrchestrator(mock_catalog).assess(request)
    sql_result = ReadinessOrchestrator(sql).assess(request)
    assert mock_result.assessment_id == sql_result.assessment_id
    assert mock_result.readiness_score == sql_result.readiness_score
    assert mock_result.confidence_score == sql_result.confidence_score


def test_simulation_parity(db_session, mock_catalog):
    from app.db.repositories.sql_repositories import SqlCatalogRepository

    sql = SqlCatalogRepository(db_session)
    request = SimulationRequest(
        project_id="azure_ai_migration",
        baseline_engineer_ids=["kavi", "vikram"],
        operation=RemoveSimulationOperation(engineer_id="kavi"),
    )
    mock_result = SimulationOrchestrator(mock_catalog).simulate(request)
    sql_result = SimulationOrchestrator(sql).simulate(request)
    assert mock_result.simulation_id == sql_result.simulation_id
    assert mock_result.readiness_score_delta == sql_result.readiness_score_delta
