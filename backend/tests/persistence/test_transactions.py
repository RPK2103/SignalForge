"""Transaction rollback tests."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.domain.enums import AuditEventType, HumanReviewState
from app.domain.persistence_models import AuditEventRecord
from app.domain.simulation_models import RemoveSimulationOperation
from app.schemas.api_v2 import ReadinessAssessRequest, SimulationRequest
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.review_persistence_service import (
    HumanReviewPersistenceService,
    HumanReviewRequest,
)
from app.services.persistence.simulation_persistence_service import SimulationPersistenceService
from sqlalchemy import func, select

from app.db.models.assessment import Assessment, AssessmentDecisionTrace, AssessmentRiskFinding
from app.db.models.audit import AuditEvent
from app.db.models.review import HumanReview
from app.db.models.simulation import Simulation


def test_assessment_rollback_when_audit_append_fails(unit_of_work, db_session):
    service = AssessmentPersistenceService(unit_of_work)
    original_append = unit_of_work.audit_events.append

    def failing_append(event: AuditEventRecord) -> None:
        if event.event_type == AuditEventType.ASSESSMENT_CREATED:
            raise RuntimeError("simulated audit failure")
        original_append(event)

    with patch.object(unit_of_work.audit_events, "append", side_effect=failing_append):
        with pytest.raises(RuntimeError):
            service.create_assessment(
                ReadinessAssessRequest(
                    project_id="azure_ai_migration",
                    engineer_ids=["kavi", "vikram"],
                )
            )

    count = db_session.scalar(select(func.count()).select_from(Assessment)) or 0
    audit_count = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    assert count == 0
    assert audit_count == 0


def test_subsequent_transaction_succeeds_after_rollback(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    with pytest.raises(RuntimeError):
        with patch.object(
            unit_of_work.audit_events,
            "append",
            side_effect=RuntimeError("simulated audit failure"),
        ):
            service.create_assessment(
                ReadinessAssessRequest(
                    project_id="azure_ai_migration",
                    engineer_ids=["kavi"],
                )
            )
    created = service.create_assessment(
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        )
    )
    assert created.assessment_record_id is not None


def test_assessment_rollback_when_risk_projection_fails(unit_of_work, db_session):
    service = AssessmentPersistenceService(unit_of_work)
    with patch.object(
        unit_of_work.assessments,
        "add_risk_projections",
        side_effect=RuntimeError("simulated risk projection failure"),
    ):
        with pytest.raises(RuntimeError):
            service.create_assessment(
                ReadinessAssessRequest(
                    project_id="azure_ai_migration",
                    engineer_ids=["kavi", "vikram"],
                )
            )

    assert (db_session.scalar(select(func.count()).select_from(Assessment)) or 0) == 0
    assert (
        db_session.scalar(select(func.count()).select_from(AssessmentRiskFinding)) or 0
    ) == 0
    assert (db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0) == 0


def test_assessment_rollback_when_trace_projection_fails(unit_of_work, db_session):
    service = AssessmentPersistenceService(unit_of_work)
    with patch.object(
        unit_of_work.assessments,
        "add_trace_projections",
        side_effect=RuntimeError("simulated trace projection failure"),
    ):
        with pytest.raises(RuntimeError):
            service.create_assessment(
                ReadinessAssessRequest(
                    project_id="azure_ai_migration",
                    engineer_ids=["kavi", "vikram"],
                )
            )

    assert (db_session.scalar(select(func.count()).select_from(Assessment)) or 0) == 0
    assert (
        db_session.scalar(select(func.count()).select_from(AssessmentDecisionTrace)) or 0
    ) == 0
    assert (db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0) == 0


def test_simulation_rollback_when_audit_append_fails(unit_of_work, db_session):
    service = SimulationPersistenceService(unit_of_work)
    with patch.object(
        unit_of_work.audit_events,
        "append",
        side_effect=RuntimeError("simulated simulation audit failure"),
    ):
        with pytest.raises(RuntimeError):
            service.create_simulation(
                SimulationRequest(
                    project_id="azure_ai_migration",
                    baseline_engineer_ids=["kavi", "vikram"],
                    operation=RemoveSimulationOperation(engineer_id="kavi"),
                )
            )

    assert (db_session.scalar(select(func.count()).select_from(Simulation)) or 0) == 0
    assert (db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0) == 0


def test_review_rollback_when_audit_append_fails(unit_of_work, db_session):
    assessments = AssessmentPersistenceService(unit_of_work)
    reviews = HumanReviewPersistenceService(unit_of_work)
    created = assessments.create_assessment(
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        )
    )

    def failing_append(event: AuditEventRecord) -> None:
        if event.event_type == AuditEventType.HUMAN_REVIEW_CREATED:
            raise RuntimeError("simulated review audit failure")
        unit_of_work.audit_events.append(event)

    with patch.object(unit_of_work.audit_events, "append", side_effect=failing_append):
        with pytest.raises(RuntimeError):
            reviews.add_review(
                created.assessment_record_id,
                HumanReviewRequest(
                    state=HumanReviewState.ACCEPTED,
                    reviewer_reference="reviewer-1",
                ),
            )

    assert (db_session.scalar(select(func.count()).select_from(HumanReview)) or 0) == 0
    audit_count = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    assert audit_count == 1
