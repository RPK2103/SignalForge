"""Audit event tests."""

from app.domain.enums import AuditEventType
from app.schemas.api_v2 import ReadinessAssessRequest
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService


def test_assessment_creates_audit_event(unit_of_work):
    service = AssessmentPersistenceService(unit_of_work)
    created = service.create_assessment(
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        )
    )
    events = unit_of_work.audit_events.list_for_aggregate(
        "assessment",
        created.assessment_record_id,
    )
    assert len(events) == 1
    assert events[0].event_type == AuditEventType.ASSESSMENT_CREATED
    assert "result_snapshot_hash" in events[0].metadata
    assert "DATABASE_URL" not in str(events[0].metadata)
