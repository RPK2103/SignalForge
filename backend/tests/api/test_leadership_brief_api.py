"""Leadership Brief API tests."""

from app.core.config import Settings
from app.domain.leadership_brief_models import LeadershipBriefFailureCategory, ProviderMode
from app.services.leadership_brief.orchestrator import LeadershipBriefOrchestrator
from app.services.leadership_brief.provider_interface import ProviderTimeoutError
from tests.leadership_brief.conftest import FakeAzureProvider, sample_evidence_package, valid_brief_from_package

ASSESSMENTS_URL = "/api/v2/assessments"


class TestLeadershipBriefApi:
    def _create_assessment(self, persistence_client):
        response = persistence_client.post(
            ASSESSMENTS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "vikram"]},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_ai_disabled_fallback(self, persistence_client, monkeypatch):
        monkeypatch.setenv("AI_ENABLED", "false")
        from app.core.config import get_settings

        get_settings.cache_clear()
        assessment = self._create_assessment(persistence_client)
        response = persistence_client.post(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-brief"
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["brief"]["provider_mode"] == ProviderMode.DETERMINISTIC_FALLBACK.value
        assert body["brief"]["generation_status"] == "fallback_generated"
        assert body["failure_category"] == LeadershipBriefFailureCategory.AI_DISABLED.value
        assert body["evidence_package_hash"]
        assert body["output_snapshot_hash"]

    def test_unknown_assessment_record(self, persistence_client):
        response = persistence_client.post(
            f"{ASSESSMENTS_URL}/00000000-0000-0000-0000-000000000000/leadership-brief"
        )
        assert response.status_code == 404
        assert response.json()["error_type"] == "record_not_found"

    def test_repeated_generation_distinct_record_ids(self, persistence_client):
        assessment = self._create_assessment(persistence_client)
        first = persistence_client.post(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-brief"
        ).json()
        second = persistence_client.post(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-brief"
        ).json()
        assert first["leadership_brief_record_id"] != second["leadership_brief_record_id"]
        assert first["output_snapshot_hash"] == second["output_snapshot_hash"]

    def test_assessment_scores_unchanged(self, persistence_client):
        assessment = self._create_assessment(persistence_client)
        before = persistence_client.get(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}"
        ).json()
        persistence_client.post(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-brief"
        )
        after = persistence_client.get(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}"
        ).json()
        assert before["result_snapshot_hash"] == after["result_snapshot_hash"]
        assert before["result"]["readiness_score"] == after["result"]["readiness_score"]
        assert before["result"]["confidence_score"] == after["result"]["confidence_score"]

    def test_list_leadership_briefs(self, persistence_client):
        assessment = self._create_assessment(persistence_client)
        persistence_client.post(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-brief"
        )
        listed = persistence_client.get(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-briefs"
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_openapi_documents_endpoint(self, persistence_client):
        schema = persistence_client.get("/openapi.json").json()
        assert "/api/v2/assessments/{assessment_record_id}/leadership-brief" in schema["paths"]

    def test_no_request_body_post(self, persistence_client):
        assessment = self._create_assessment(persistence_client)
        response = persistence_client.post(
            f"{ASSESSMENTS_URL}/{assessment['assessment_record_id']}/leadership-brief"
        )
        assert response.status_code == 200
