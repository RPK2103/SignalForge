"""End-to-end integration tests for the v2 team simulation API flow."""

from fastapi.testclient import TestClient

from app.domain.policy import get_policy
from app.main import app

client = TestClient(app)

SIMULATE_URL = "/api/v2/simulations"
ASSESS_URL = "/api/v2/readiness/assess"
ENGINEERS_URL = "/api/v2/engineers"
PROJECTS_URL = "/api/v2/projects"


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


class TestSimulationV2CatalogFlow:
    def test_catalog_driven_simulation_flow(self):
        projects = client.get(PROJECTS_URL).json()["projects"]
        assert projects
        project_id = projects[0]["id"]

        engineers = client.get(ENGINEERS_URL).json()["engineers"]
        assert len(engineers) >= 2
        baseline_ids = [engineers[0]["id"], engineers[1]["id"]]

        baseline_assessment = client.post(
            ASSESS_URL,
            json={"project_id": project_id, "engineer_ids": baseline_ids},
        )
        assert baseline_assessment.status_code == 200, baseline_assessment.text

        add_response = client.post(
            SIMULATE_URL,
            json={
                "project_id": project_id,
                "baseline_engineer_ids": baseline_ids,
                "operation": {"type": "add", "engineer_id": engineers[2]["id"]},
            },
        )
        assert add_response.status_code == 200, add_response.text
        add_body = add_response.json()
        assert len(add_body["proposed_team"]) == len(baseline_ids) + 1

        remove_response = client.post(
            SIMULATE_URL,
            json={
                "project_id": project_id,
                "baseline_engineer_ids": baseline_ids,
                "operation": {"type": "remove", "engineer_id": baseline_ids[0]},
            },
        )
        assert remove_response.status_code == 200, remove_response.text
        remove_body = remove_response.json()
        assert remove_body["readiness_score_delta"] <= 0

        replace_response = client.post(
            SIMULATE_URL,
            json={
                "project_id": project_id,
                "baseline_engineer_ids": baseline_ids,
                "operation": {
                    "type": "replace",
                    "remove_engineer_id": baseline_ids[0],
                    "add_engineer_id": engineers[2]["id"],
                },
            },
        )
        assert replace_response.status_code == 200, replace_response.text

        compare_response = client.post(
            SIMULATE_URL,
            json={
                "project_id": project_id,
                "baseline_engineer_ids": baseline_ids,
                "operation": {
                    "type": "compare",
                    "proposed_engineer_ids": [engineers[2]["id"]],
                },
            },
        )
        assert compare_response.status_code == 200, compare_response.text

        repeat = client.post(
            SIMULATE_URL,
            json={
                "project_id": project_id,
                "baseline_engineer_ids": baseline_ids,
                "operation": {"type": "remove", "engineer_id": baseline_ids[0]},
            },
        ).json()
        assert repeat == remove_body

        reversed_baseline = client.post(
            SIMULATE_URL,
            json={
                "project_id": project_id,
                "baseline_engineer_ids": list(reversed(baseline_ids)),
                "operation": {"type": "remove", "engineer_id": baseline_ids[0]},
            },
        ).json()
        assert reversed_baseline["simulation_id"] == remove_body["simulation_id"]

        assert remove_body["policy_version"] == get_policy().POLICY_VERSION
        assert round(_readiness_trace_total(remove_body["baseline_assessment"]), 2) == float(
            remove_body["baseline_assessment"]["readiness_score"]
        )
        assert round(_confidence_trace_total(remove_body["baseline_assessment"]), 2) == float(
            remove_body["baseline_assessment"]["confidence_score"]
        )

        readiness_delta = sum(
            entry["contribution_delta"]
            for entry in remove_body["decision_trace_delta"]
            if entry["step"] == "readiness"
        )
        assert round(readiness_delta, 2) == float(remove_body["readiness_score_delta"])

        for mitigation in remove_body["recommended_mitigations"]:
            assert mitigation["evidence_references"]

    def test_kavi_removal_scenario(self):
        payload = {
            "project_id": "azure_ai_migration",
            "baseline_engineer_ids": ["kavi", "vikram"],
            "operation": {"type": "remove", "engineer_id": "kavi"},
        }
        response = client.post(SIMULATE_URL, json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["readiness_score_delta"] < 0
        assert body["baseline_assessment"]["readiness_score"] > body["proposed_assessment"]["readiness_score"]
        assert any(
            gap.get("is_critical")
            for gap in body["newly_introduced_gaps"]
        ) or any(
            change["change_type"] in {"degraded", "modified"}
            for change in body["capability_coverage_changes"]
        )

    def test_legacy_simulate_registered(self):
        openapi = client.get("/openapi.json").json()["paths"]
        assert "/simulate" in openapi
        response = client.post(
            "/simulate",
            json={"project_name": "Azure AI Migration", "remove_engineers": ["Kavi"]},
        )
        assert response.status_code == 200, response.text
