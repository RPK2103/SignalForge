"""End-to-end integration tests for the v2 readiness API flow."""

from fastapi.testclient import TestClient

from app.domain.policy import get_policy
from app.main import app

client = TestClient(app)

ASSESS_URL = "/api/v2/readiness/assess"
ENGINEERS_URL = "/api/v2/engineers"
PROJECTS_URL = "/api/v2/projects"

LEGACY_POST_ROUTES = [
    "/analyze",
    "/project-fit",
    "/assess-risk",
    "/recommend-team",
    "/generate-insight",
    "/simulate",
    "/success-prediction",
    "/copilot",
]


def _readiness_trace_total(body: dict) -> float:
    return sum(
        entry["contribution"]
        for entry in body["decision_trace"]
        if entry["step"] == "readiness"
    )


def _confidence_trace_total(body: dict) -> float:
    return sum(
        entry["contribution"]
        for entry in body["decision_trace"]
        if entry["step"] == "confidence"
    )


class TestReadinessV2CatalogFlow:
    def test_catalog_driven_assessment_is_deterministic(self):
        projects = client.get(PROJECTS_URL).json()["projects"]
        assert projects
        project_id = projects[0]["id"]

        engineers = client.get(ENGINEERS_URL).json()["engineers"]
        assert len(engineers) >= 2
        engineer_ids = [engineers[0]["id"], engineers[1]["id"]]

        payload = {"project_id": project_id, "engineer_ids": engineer_ids}
        first = client.post(ASSESS_URL, json=payload)
        second = client.post(ASSESS_URL, json=payload)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        first_body = first.json()
        second_body = second.json()

        assert first_body["project_id"] == project_id
        assert {member["id"] for member in first_body["team"]} == set(engineer_ids)
        assert len(first_body["team"]) == len(set(engineer_ids))
        assert first_body["policy_version"] == get_policy().POLICY_VERSION
        assert round(_readiness_trace_total(first_body), 2) == float(
            first_body["readiness_score"]
        )
        assert round(_confidence_trace_total(first_body), 2) == float(
            first_body["confidence_score"]
        )
        assert first_body == second_body

    def test_reversed_engineer_order_matches_forward_request(self):
        projects = client.get(PROJECTS_URL).json()["projects"]
        engineers = client.get(ENGINEERS_URL).json()["engineers"]
        project_id = projects[0]["id"]
        engineer_ids = [engineers[0]["id"], engineers[1]["id"]]

        forward = client.post(
            ASSESS_URL,
            json={"project_id": project_id, "engineer_ids": engineer_ids},
        ).json()
        reversed_team = client.post(
            ASSESS_URL,
            json={"project_id": project_id, "engineer_ids": list(reversed(engineer_ids))},
        ).json()

        assert forward["readiness_score"] == reversed_team["readiness_score"]
        assert forward["confidence_score"] == reversed_team["confidence_score"]
        assert forward["assessment_id"] == reversed_team["assessment_id"]
        assert forward["decision_trace"] == reversed_team["decision_trace"]

    def test_legacy_routes_remain_registered(self):
        openapi = client.get("/openapi.json").json()["paths"]
        for route in LEGACY_POST_ROUTES:
            assert route in openapi
