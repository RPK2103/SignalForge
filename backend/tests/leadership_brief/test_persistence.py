"""Leadership Brief persistence tests."""

from uuid import UUID

from app.domain.enums import AuditEventType
from app.services.leadership_brief.orchestrator import LeadershipBriefOrchestrator
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.leadership_brief_persistence_service import (
    LeadershipBriefPersistenceService,
)
from app.schemas.api_v2 import ReadinessAssessRequest


class TestLeadershipBriefPersistence:
    def test_persist_and_list(self, unit_of_work):
        assessment_service = AssessmentPersistenceService(unit_of_work)
        created = assessment_service.create_assessment(
            ReadinessAssessRequest(
                project_id="azure_ai_migration",
                engineer_ids=["kavi", "vikram"],
            )
        )
        brief_service = LeadershipBriefPersistenceService(
            unit_of_work,
            orchestrator=LeadershipBriefOrchestrator(),
        )
        generated = brief_service.generate_leadership_brief(created.assessment_record_id)
        assert generated.brief.provider_mode.value == "deterministic_fallback"
        listed = brief_service.list_leadership_briefs(created.assessment_record_id)
        assert len(listed) == 1
        assert listed[0].output_snapshot_hash == generated.output_snapshot_hash

    def test_append_only_repeated_generation(self, unit_of_work):
        assessment_service = AssessmentPersistenceService(unit_of_work)
        created = assessment_service.create_assessment(
            ReadinessAssessRequest(
                project_id="azure_ai_migration",
                engineer_ids=["kavi", "vikram"],
            )
        )
        brief_service = LeadershipBriefPersistenceService(
            unit_of_work,
            orchestrator=LeadershipBriefOrchestrator(),
        )
        first = brief_service.generate_leadership_brief(created.assessment_record_id)
        second = brief_service.generate_leadership_brief(created.assessment_record_id)
        assert first.leadership_brief_record_id != second.leadership_brief_record_id
        assert first.output_snapshot_hash == second.output_snapshot_hash
        assert len(brief_service.list_leadership_briefs(created.assessment_record_id)) == 2

    def test_audit_event_created(self, unit_of_work, db_session):
        assessment_service = AssessmentPersistenceService(unit_of_work)
        created = assessment_service.create_assessment(
            ReadinessAssessRequest(
                project_id="azure_ai_migration",
                engineer_ids=["kavi", "vikram"],
            )
        )
        brief_service = LeadershipBriefPersistenceService(
            unit_of_work,
            orchestrator=LeadershipBriefOrchestrator(),
        )
        generated = brief_service.generate_leadership_brief(created.assessment_record_id)
        from app.db.repositories.sql_repositories import SqlAuditEventRepository

        audit = SqlAuditEventRepository(db_session)
        events = audit.list_for_aggregate("assessment", created.assessment_record_id)
        brief_events = [
            event for event in events if event.event_type == AuditEventType.LEADERSHIP_BRIEF_CREATED
        ]
        assert len(brief_events) == 1
        assert "leadership_brief_record_id" in brief_events[0].metadata
        assert "AZURE_OPENAI" not in str(brief_events[0].metadata)

    def test_assessment_unchanged(self, unit_of_work):
        assessment_service = AssessmentPersistenceService(unit_of_work)
        created = assessment_service.create_assessment(
            ReadinessAssessRequest(
                project_id="azure_ai_migration",
                engineer_ids=["kavi", "vikram"],
            )
        )
        before = assessment_service.get_assessment(created.assessment_record_id)
        brief_service = LeadershipBriefPersistenceService(
            unit_of_work,
            orchestrator=LeadershipBriefOrchestrator(),
        )
        brief_service.generate_leadership_brief(created.assessment_record_id)
        after = assessment_service.get_assessment(created.assessment_record_id)
        assert before.result_snapshot_hash == after.result_snapshot_hash
        assert before.result.readiness_score == after.result.readiness_score
