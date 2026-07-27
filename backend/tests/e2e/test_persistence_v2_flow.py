"""End-to-end persistence flow."""

from app.domain.enums import AuditEventType, HumanReviewState

ASSESSMENTS_URL = "/api/v2/assessments"
SIM_RECORDS_URL = "/api/v2/simulation-records"


class TestPersistenceV2Flow:
    def test_full_persistence_flow(self, persistence_client, db_session):
        create = persistence_client.post(
            ASSESSMENTS_URL,
            json={
                "project_id": "azure_ai_migration",
                "engineer_ids": ["kavi", "vikram"],
            },
        )
        assert create.status_code == 200
        assessment = create.json()
        record_id = assessment["assessment_record_id"]

        detail = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}").json()
        assert detail["result"]["assessment_id"] == assessment["assessment_id"]

        review = persistence_client.post(
            f"{ASSESSMENTS_URL}/{record_id}/reviews",
            json={"state": "accepted", "reviewer_reference": "lead"},
        )
        assert review.status_code == 200
        assert review.json()["latest_review_state"] == HumanReviewState.ACCEPTED.value

        sim = persistence_client.post(
            SIM_RECORDS_URL,
            json={
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "remove", "engineer_id": "kavi"},
            },
        )
        assert sim.status_code == 200
        sim_id = sim.json()["simulation_record_id"]
        sim_detail = persistence_client.get(f"{SIM_RECORDS_URL}/{sim_id}").json()
        assert (
            sim_detail["result"]["readiness_score_delta"]
            == sim.json()["result"]["readiness_score_delta"]
        )

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

        historical = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}").json()
        assert historical["result_snapshot_hash"] == assessment["result_snapshot_hash"]

        from uuid import UUID

        from app.db.repositories.sql_repositories import SqlAuditEventRepository

        audit = SqlAuditEventRepository(db_session)
        events = audit.list_for_aggregate(
            "assessment",
            UUID(assessment["assessment_record_id"]),
        )
        assert events[0].event_type == AuditEventType.ASSESSMENT_CREATED

        compute = persistence_client.post(
            "/api/v2/readiness/assess",
            json={
                "project_id": "azure_ai_migration",
                "engineer_ids": ["kavi", "vikram"],
            },
        )
        assert compute.status_code == 200
