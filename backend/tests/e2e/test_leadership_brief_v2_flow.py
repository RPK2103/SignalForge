"""End-to-end Leadership Brief flow."""

from uuid import UUID

from app.db.repositories.sql_repositories import SqlAuditEventRepository
from app.domain.enums import AuditEventType

ASSESSMENTS_URL = "/api/v2/assessments"


class TestLeadershipBriefV2Flow:
    def test_full_leadership_brief_flow(self, persistence_client, db_session, monkeypatch):
        monkeypatch.setenv("AI_ENABLED", "false")
        from app.core.config import get_settings

        get_settings.cache_clear()

        create = persistence_client.post(
            ASSESSMENTS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "vikram"]},
        )
        assert create.status_code == 200
        assessment = create.json()
        record_id = assessment["assessment_record_id"]

        first = persistence_client.post(f"{ASSESSMENTS_URL}/{record_id}/leadership-brief")
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["brief"]["provider_mode"] == "deterministic_fallback"
        assert first_body["brief"]["generation_status"] == "fallback_generated"
        assert first_body["failure_category"] == "ai_disabled"
        assert first_body["brief"]["prompt_version"] == "leadership-brief-v1"

        known_refs = set(first_body["brief"]["evidence_references"])
        for risk in first_body["brief"]["top_risks"]:
            assert all(ref in known_refs for ref in risk["evidence_references"])
        for action in (
            first_body["brief"]["staffing_actions"] + first_body["brief"]["mitigation_actions"]
        ):
            assert all(ref in known_refs for ref in action["evidence_references"])

        detail_before = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}").json()
        second = persistence_client.post(f"{ASSESSMENTS_URL}/{record_id}/leadership-brief")
        assert second.status_code == 200
        second_body = second.json()
        assert first_body["leadership_brief_record_id"] != second_body["leadership_brief_record_id"]
        assert first_body["output_snapshot_hash"] == second_body["output_snapshot_hash"]

        detail_after = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}").json()
        assert detail_before["result_snapshot_hash"] == detail_after["result_snapshot_hash"]

        listed = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}/leadership-briefs").json()
        assert len(listed) == 2

        audit = SqlAuditEventRepository(db_session)
        events = audit.list_for_aggregate("assessment", UUID(record_id))
        brief_events = [
            event for event in events if event.event_type == AuditEventType.LEADERSHIP_BRIEF_CREATED
        ]
        assert len(brief_events) == 2

        review = persistence_client.post(
            f"{ASSESSMENTS_URL}/{record_id}/reviews",
            json={"state": "accepted", "reviewer_reference": "lead"},
        )
        assert review.status_code == 200
        brief_after_review = persistence_client.get(
            f"{ASSESSMENTS_URL}/{record_id}/leadership-briefs"
        ).json()
        assert brief_after_review[0]["output_snapshot_hash"] == first_body["output_snapshot_hash"]

        from sqlalchemy import select

        from app.db.models.catalog import EngineerCapability

        cap = db_session.scalar(
            select(EngineerCapability).where(
                EngineerCapability.engineer_id == "kavi",
                EngineerCapability.capability_id == "generative_ai",
            )
        )
        cap.proficiency = 1
        db_session.commit()

        third = persistence_client.post(f"{ASSESSMENTS_URL}/{record_id}/leadership-brief")
        assert third.status_code == 200
        third_body = third.json()
        assert third_body["brief"]["provider_mode"] == "deterministic_fallback"
        assert (
            str(detail_after["result"]["readiness_score"])
            in third_body["brief"]["executive_summary"]
        )
        final_detail = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}").json()
        assert final_detail["result_snapshot_hash"] == assessment["result_snapshot_hash"]

        compute = persistence_client.post(
            "/api/v2/readiness/assess",
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "vikram"]},
        )
        assert compute.status_code == 200
