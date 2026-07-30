"""Snapshot immutability tests."""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models.assessment import Assessment
from app.db.models.catalog import EngineerCapability
from app.db.models.simulation import Simulation
from app.domain.simulation_models import RemoveSimulationOperation
from app.schemas.api_v2 import ReadinessAssessRequest, SimulationRequest
from app.security.context import internal_system_context
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.exceptions import SnapshotIntegrityError
from app.services.persistence.simulation_persistence_service import SimulationPersistenceService

CTX = internal_system_context("novabank", correlation_id="test")


def test_assessment_snapshot_survives_catalog_change(db_session, unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    created = service.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    cap = db_session.scalar(
        select(EngineerCapability).where(
            EngineerCapability.engineer_id == "kavi",
            EngineerCapability.capability_id == "generative_ai",
        )
    )
    assert cap is not None
    cap.proficiency = 10
    db_session.commit()

    loaded = service.get_assessment(created.assessment_record_id)
    assert loaded.result_snapshot_hash == created.result_snapshot_hash
    assert loaded.result.readiness_score == created.result.readiness_score

    newer = service.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    assert newer.result.readiness_score != created.result.readiness_score


def test_simulation_snapshot_survives_catalog_change(db_session, unit_of_work):
    service = SimulationPersistenceService(unit_of_work)
    created = service.create_simulation(
        CTX,
        SimulationRequest(
            project_id="azure_ai_migration",
            baseline_engineer_ids=["kavi", "vikram"],
            operation=RemoveSimulationOperation(engineer_id="kavi"),
        ),
    )
    cap = db_session.scalar(
        select(EngineerCapability).where(
            EngineerCapability.engineer_id == "vikram",
            EngineerCapability.capability_id == "python",
        )
    )
    assert cap is not None
    cap.proficiency = 5
    db_session.commit()

    loaded = service.get_simulation(created.simulation_record_id)
    assert loaded.result_snapshot_hash == created.result_snapshot_hash
    assert loaded.result.readiness_score_delta == created.result.readiness_score_delta


def test_get_assessment_does_not_recompute(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    created = service.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    with patch.object(
        service._orchestrator,
        "assess",
        side_effect=AssertionError("GET must not recompute readiness"),
    ):
        loaded = service.get_assessment(created.assessment_record_id)
    assert loaded.result_snapshot_hash == created.result_snapshot_hash


def test_get_simulation_does_not_recompute(unit_of_work):
    service = SimulationPersistenceService(unit_of_work)
    created = service.create_simulation(
        CTX,
        SimulationRequest(
            project_id="azure_ai_migration",
            baseline_engineer_ids=["kavi", "vikram"],
            operation=RemoveSimulationOperation(engineer_id="kavi"),
        ),
    )
    with patch.object(
        service._orchestrator,
        "simulate",
        side_effect=AssertionError("GET must not recompute simulation"),
    ):
        loaded = service.get_simulation(created.simulation_record_id)
    assert loaded.result_snapshot_hash == created.result_snapshot_hash


def test_assessment_result_hash_mismatch_fails(db_session, unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    created = service.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    row = db_session.get(Assessment, created.assessment_record_id)
    row.result_snapshot_hash = "0" * 64
    db_session.commit()

    with pytest.raises(SnapshotIntegrityError):
        service.get_assessment(created.assessment_record_id)


def test_simulation_baseline_hash_mismatch_fails(db_session, unit_of_work):
    service = SimulationPersistenceService(unit_of_work)
    created = service.create_simulation(
        CTX,
        SimulationRequest(
            project_id="azure_ai_migration",
            baseline_engineer_ids=["kavi", "vikram"],
            operation=RemoveSimulationOperation(engineer_id="kavi"),
        ),
    )
    row = db_session.get(Simulation, created.simulation_record_id)
    row.baseline_snapshot_hash = "0" * 64
    db_session.commit()

    with pytest.raises(SnapshotIntegrityError):
        service.get_simulation(created.simulation_record_id)
