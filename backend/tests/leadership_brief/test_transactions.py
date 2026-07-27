"""Leadership Brief transaction rollback tests."""

from unittest.mock import patch

from app.db.repositories.sql_repositories import SqlAuditEventRepository
from app.domain.enums import AuditEventType
from app.schemas.api_v2 import ReadinessAssessRequest
from app.services.leadership_brief.orchestrator import LeadershipBriefOrchestrator
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.leadership_brief_persistence_service import (
    LeadershipBriefPersistenceService,
)


class TestLeadershipBriefTransactions:
    def _create_assessment(self, unit_of_work):
        service = AssessmentPersistenceService(unit_of_work)
        return service.create_assessment(
            ReadinessAssessRequest(
                project_id="azure_ai_migration",
                engineer_ids=["kavi", "vikram"],
            )
        )

    def test_rollback_when_audit_append_fails(self, unit_of_work, db_session):
        created = self._create_assessment(unit_of_work)
        brief_service = LeadershipBriefPersistenceService(
            unit_of_work,
            orchestrator=LeadershipBriefOrchestrator(),
        )
        with patch.object(
            unit_of_work.audit_events,
            "append",
            side_effect=RuntimeError("audit failed"),
        ):
            try:
                brief_service.generate_leadership_brief(created.assessment_record_id)
            except RuntimeError:
                pass
        listed = brief_service.list_leadership_briefs(created.assessment_record_id)
        assert listed == []
        audit = SqlAuditEventRepository(db_session)
        events = audit.list_for_aggregate("assessment", created.assessment_record_id)
        assert all(event.event_type != AuditEventType.LEADERSHIP_BRIEF_CREATED for event in events)

    def test_subsequent_transaction_succeeds_after_rollback(self, unit_of_work):
        created = self._create_assessment(unit_of_work)
        brief_service = LeadershipBriefPersistenceService(
            unit_of_work,
            orchestrator=LeadershipBriefOrchestrator(),
        )
        with patch.object(
            unit_of_work.leadership_briefs,
            "add",
            side_effect=RuntimeError("insert failed"),
        ):
            try:
                brief_service.generate_leadership_brief(created.assessment_record_id)
            except RuntimeError:
                pass
        generated = brief_service.generate_leadership_brief(created.assessment_record_id)
        assert generated.leadership_brief_record_id is not None
