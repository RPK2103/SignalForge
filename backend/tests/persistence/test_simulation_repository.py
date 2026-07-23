"""Simulation repository tests."""

from uuid import uuid4

import pytest

from app.domain.simulation_models import RemoveSimulationOperation
from app.schemas.api_v2 import SimulationRequest
from app.services.persistence.simulation_persistence_service import SimulationPersistenceService


def test_create_and_retrieve_simulation(unit_of_work):
    service = SimulationPersistenceService(unit_of_work)
    created = service.create_simulation(
        SimulationRequest(
            project_id="azure_ai_migration",
            baseline_engineer_ids=["kavi", "vikram"],
            operation=RemoveSimulationOperation(engineer_id="kavi"),
        )
    )
    loaded = service.get_simulation(created.simulation_record_id)
    assert loaded.simulation_id == created.simulation_id
    assert loaded.result.readiness_score_delta == created.result.readiness_score_delta


def test_distinct_records_same_simulation_id(unit_of_work):
    service = SimulationPersistenceService(unit_of_work)
    request = SimulationRequest(
        project_id="azure_ai_migration",
        baseline_engineer_ids=["kavi", "vikram"],
        operation=RemoveSimulationOperation(engineer_id="kavi"),
    )
    first = service.create_simulation(request)
    second = service.create_simulation(request)
    assert first.simulation_id == second.simulation_id
    assert first.simulation_record_id != second.simulation_record_id


def test_unknown_record(unit_of_work):
    service = SimulationPersistenceService(unit_of_work)
    from app.services.persistence.exceptions import RecordNotFoundError

    with pytest.raises(RecordNotFoundError):
        service.get_simulation(uuid4())
