"""Assessment repository tests."""

from uuid import uuid4

import pytest

from app.schemas.api_v2 import ReadinessAssessRequest
from app.security.context import internal_system_context
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService

# Authorized tenant-admin context for direct service-layer calls (deny-by-default
# authorization now requires a valid SecurityContext).
CTX = internal_system_context("novabank", correlation_id="test")


def test_create_and_retrieve_assessment(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    created = service.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    loaded = service.get_assessment(created.assessment_record_id)
    assert loaded.assessment_id == created.assessment_id
    assert loaded.result.readiness_score == created.result.readiness_score
    assert loaded.result_snapshot_hash == created.result_snapshot_hash


def test_repeated_assessment_same_deterministic_id_distinct_records(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    request = ReadinessAssessRequest(
        project_id="azure_ai_migration",
        engineer_ids=["kavi", "vikram"],
    )
    first = service.create_assessment(CTX, request)
    second = service.create_assessment(CTX, request)
    assert first.assessment_id == second.assessment_id
    assert first.assessment_record_id != second.assessment_record_id


def test_list_newest_first(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    request = ReadinessAssessRequest(
        project_id="azure_ai_migration",
        engineer_ids=["kavi"],
    )
    service.create_assessment(CTX, request)
    second = service.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    listing = service.list_assessments(limit=10)
    assert listing.items[0].assessment_record_id == second.assessment_record_id


def test_unknown_record(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    from app.services.persistence.exceptions import RecordNotFoundError

    with pytest.raises(RecordNotFoundError):
        service.get_assessment(uuid4())
