"""Assessment history API tests."""

ASSESSMENTS_URL = "/api/v2/assessments"


class TestAssessmentHistoryApi:
    def test_create_and_get(self, persistence_client):
        create = persistence_client.post(
            ASSESSMENTS_URL,
            json={
                "project_id": "azure_ai_migration",
                "engineer_ids": ["kavi", "vikram"],
            },
        )
        assert create.status_code == 200, create.text
        body = create.json()
        record_id = body["assessment_record_id"]
        get_resp = persistence_client.get(f"{ASSESSMENTS_URL}/{record_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["result"]["readiness_score"] == body["result"]["readiness_score"]

    def test_list_and_pagination(self, persistence_client):
        persistence_client.post(
            ASSESSMENTS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi"]},
        )
        listing = persistence_client.get(f"{ASSESSMENTS_URL}?limit=1&offset=0")
        assert listing.status_code == 200
        data = listing.json()
        assert data["limit"] == 1
        assert data["total"] >= 1

    def test_unsupported_content_type(self, persistence_client):
        response = persistence_client.post(
            ASSESSMENTS_URL,
            content=b"not-json",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 415
        assert response.json()["error_type"] == "unsupported_media_type"

    def test_unknown_record(self, persistence_client):
        response = persistence_client.get(f"{ASSESSMENTS_URL}/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["error_type"] == "record_not_found"
