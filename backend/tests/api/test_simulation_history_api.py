"""Simulation history API tests."""

SIM_RECORDS_URL = "/api/v2/simulation-records"


class TestSimulationHistoryApi:
    def test_create_remove_simulation(self, persistence_client):
        response = persistence_client.post(
            SIM_RECORDS_URL,
            json={
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "remove", "engineer_id": "kavi"},
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        get_resp = persistence_client.get(
            f"{SIM_RECORDS_URL}/{body['simulation_record_id']}"
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["simulation_id"] == body["simulation_id"]

    def test_unsupported_content_type(self, persistence_client):
        response = persistence_client.post(
            SIM_RECORDS_URL,
            content=b"{}",
            headers={"Content-Type": "application/xml"},
        )
        assert response.status_code == 415
