"""API tests for versioned team simulation endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.domain.policy import get_policy
from app.main import app
from tests.support.auth import broad_tenant_headers

client = TestClient(app, headers=broad_tenant_headers())

SIMULATE_URL = "/api/v2/simulations"
PROJECT_ID = "azure_ai_migration"
BASELINE = ["kavi", "vikram"]


def _remove_payload(engineer_id: str = "kavi"):
    return {
        "project_id": PROJECT_ID,
        "baseline_engineer_ids": BASELINE,
        "operation": {"type": "remove", "engineer_id": engineer_id},
    }


class TestSuccessfulSimulations:
    def test_remove_simulation(self):
        response = client.post(SIMULATE_URL, json=_remove_payload())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["simulation_id"]
        assert body["operation"]["type"] == "remove"
        assert body["readiness_score_delta"] <= 0
        assert len(body["baseline_team"]) == 2
        assert len(body["proposed_team"]) == 1

    def test_add_simulation(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {"type": "add", "engineer_id": "arjun"},
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["operation"]["type"] == "add"
        assert len(body["proposed_team"]) == 3

    def test_replace_simulation(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {
                    "type": "replace",
                    "remove_engineer_id": "kavi",
                    "add_engineer_id": "arjun",
                },
            },
        )
        assert response.status_code == 200, response.text
        proposed_ids = {member["id"] for member in response.json()["proposed_team"]}
        assert "arjun" in proposed_ids
        assert "kavi" not in proposed_ids

    def test_compare_simulation(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {
                    "type": "compare",
                    "proposed_engineer_ids": ["arjun"],
                },
            },
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["proposed_team"]) == 1

    def test_unchanged_compare_zero_deltas(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {
                    "type": "compare",
                    "proposed_engineer_ids": BASELINE,
                },
            },
        )
        body = response.json()
        assert body["readiness_score_delta"] == 0
        assert body["confidence_delta"] == 0

    def test_empty_proposed_team(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {"type": "compare", "proposed_engineer_ids": []},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["proposed_team"] == []


class TestSimulationErrors:
    def test_unknown_project(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": "unknown_project",
                "baseline_engineer_ids": BASELINE,
                "operation": {"type": "remove", "engineer_id": "kavi"},
            },
        )
        assert response.status_code == 404
        assert response.json()["error_type"] == "http_error"

    def test_unknown_baseline_engineer(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": ["unknown"],
                "operation": {"type": "remove", "engineer_id": "unknown"},
            },
        )
        assert response.status_code == 404

    def test_unknown_incoming_engineer(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {"type": "add", "engineer_id": "unknown"},
            },
        )
        assert response.status_code == 404

    def test_invalid_removal(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {"type": "remove", "engineer_id": "arjun"},
            },
        )
        assert response.status_code == 409
        assert response.json()["error_type"] == "http_error"

    def test_duplicate_addition(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {"type": "add", "engineer_id": "kavi"},
            },
        )
        assert response.status_code == 409

    def test_invalid_replacement(self):
        response = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": BASELINE,
                "operation": {
                    "type": "replace",
                    "remove_engineer_id": "kavi",
                    "add_engineer_id": "kavi",
                },
            },
        )
        assert response.status_code == 400


class TestDeterministicSimulationApi:
    def test_repeated_request_equality(self):
        payload = _remove_payload()
        first = client.post(SIMULATE_URL, json=payload).json()
        second = client.post(SIMULATE_URL, json=payload).json()
        assert first == second

    def test_reordered_baseline_same_id(self):
        forward = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": ["kavi", "vikram", "arjun"],
                "operation": {"type": "remove", "engineer_id": "arjun"},
            },
        ).json()
        reversed_team = client.post(
            SIMULATE_URL,
            json={
                "project_id": PROJECT_ID,
                "baseline_engineer_ids": ["arjun", "vikram", "kavi"],
                "operation": {"type": "remove", "engineer_id": "arjun"},
            },
        ).json()
        assert forward["simulation_id"] == reversed_team["simulation_id"]


class TestContentTypeEnforcement:
    @pytest.mark.parametrize(
        "content_type",
        [
            "application/json",
            "application/json; charset=utf-8",
            "application/vnd.api+json",
        ],
    )
    def test_json_content_types_accepted(self, content_type):
        response = client.post(
            SIMULATE_URL,
            json=_remove_payload(),
            headers={"Content-Type": content_type},
        )
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize(
        "content_type",
        ["text/plain", "application/xml"],
    )
    def test_non_json_content_type_rejected(self, content_type):
        response = client.post(
            SIMULATE_URL,
            content='{"project_id":"azure_ai_migration","baseline_engineer_ids":["kavi"],"operation":{"type":"remove","engineer_id":"kavi"}}',
            headers={"Content-Type": content_type},
        )
        assert response.status_code == 415
        assert response.json()["error_type"] == "unsupported_media_type"

    def test_missing_content_type_rejected(self):
        response = client.post(
            SIMULATE_URL,
            content='{"project_id":"azure_ai_migration","baseline_engineer_ids":["kavi"],"operation":{"type":"remove","engineer_id":"kavi"}}',
        )
        assert response.status_code == 415


class TestOpenApiContract:
    def test_simulations_endpoint_documented(self):
        openapi = client.get("/openapi.json").json()
        path = openapi["paths"]["/api/v2/simulations"]["post"]
        assert path["operationId"]
        assert "415" in path["responses"]
        assert "422" in path["responses"]
        request_schema = path["requestBody"]["content"]["application/json"]["schema"]
        assert "$ref" in request_schema or "properties" in request_schema

    def test_operation_discriminator_variants(self):
        openapi = client.get("/openapi.json").json()
        components = openapi["components"]["schemas"]
        assert any("AddSimulationOperation" in name for name in components)
        assert any("RemoveSimulationOperation" in name for name in components)


class TestLegacySimulateRegression:
    def test_legacy_simulate_still_works(self):
        response = client.post(
            "/simulate",
            json={"project_name": "Azure AI Migration", "remove_engineers": ["Kavi"]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["removed_engineers"] == ["Kavi"]
        assert "Kavi" not in body["remaining_team"]
        assert body["coverage_after"] <= body["coverage_before"]


class TestSimulationResponseShape:
    def test_full_response_model(self):
        response = client.post(SIMULATE_URL, json=_remove_payload())
        body = response.json()
        assert body["policy_version"] == get_policy().POLICY_VERSION
        for key in (
            "baseline_assessment",
            "proposed_assessment",
            "risk_level_changes",
            "capability_coverage_changes",
            "newly_introduced_gaps",
            "resolved_gaps",
            "key_person_dependency_changes",
            "decision_trace_delta",
            "recommended_mitigations",
        ):
            assert key in body

    def test_mitigations_reference_evidence(self):
        body = client.post(SIMULATE_URL, json=_remove_payload()).json()
        for mitigation in body["recommended_mitigations"]:
            assert mitigation["mitigation_id"]
            assert mitigation["evidence_references"]

    def test_decision_trace_reconciliation(self):
        body = client.post(SIMULATE_URL, json=_remove_payload()).json()
        readiness_delta = sum(
            entry["contribution_delta"]
            for entry in body["decision_trace_delta"]
            if entry["step"] == "readiness"
        )
        assert round(readiness_delta, 2) == float(body["readiness_score_delta"])
