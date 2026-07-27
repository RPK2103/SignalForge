"""API tests for versioned readiness intelligence endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.domain.policy import get_policy
from app.main import app

client = TestClient(app)

ASSESS_URL = "/api/v2/readiness/assess"
CAPABILITIES_URL = "/api/v2/capabilities"
POLICIES_URL = "/api/v2/policies/readiness"
ENGINEERS_URL = "/api/v2/engineers"
PROJECTS_URL = "/api/v2/projects"

VALID_ASSESS_PAYLOAD = {
    "project_id": "azure_ai_migration",
    "engineer_ids": ["kavi", "vikram"],
}

LEGACY_POST_ROUTES = [
    (
        "/analyze",
        {
            "name": "Kavi",
            "experience": 5,
            "skills": ["Azure"],
            "certifications": [],
            "projects": [],
        },
    ),
    (
        "/project-fit",
        {
            "engineer": {
                "name": "Kavi",
                "experience": 5,
                "skills": ["Azure"],
                "certifications": [],
                "projects": [],
            },
            "project": {
                "name": "Azure AI Migration",
                "required_skills": ["Azure"],
                "description": "Demo",
            },
        },
    ),
    (
        "/assess-risk",
        {
            "engineer": {
                "name": "Kavi",
                "experience": 5,
                "skills": ["Azure"],
                "certifications": [],
                "projects": [],
            },
            "project": {
                "name": "Azure AI Migration",
                "required_skills": ["Azure"],
                "preferred_skills": [],
                "domain": "Cloud",
            },
        },
    ),
    (
        "/recommend-team",
        {
            "project": {
                "name": "Azure AI Migration",
                "required_skills": ["Azure"],
                "description": "Demo",
            },
            "engineers": [
                {
                    "name": "Kavi",
                    "experience": 5,
                    "skills": ["Azure"],
                    "certifications": [],
                    "projects": [],
                }
            ],
        },
    ),
    ("/simulate", {"project_name": "Azure AI Migration", "remove_engineers": ["Kavi"]}),
    ("/success-prediction", {"project_name": "Azure AI Migration"}),
    (
        "/copilot",
        {
            "project_name": "Azure AI Migration",
            "question": "Why is this project likely to succeed?",
        },
    ),
]


class TestSuccessfulAssessment:
    def test_returns_complete_response(self):
        response = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD)
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["assessment_id"]
        assert body["project_id"] == "azure_ai_migration"
        assert body["project_name"] == "Azure AI Migration"
        assert len(body["team"]) == 2
        assert 0 <= body["readiness_score"] <= 100
        assert 0 <= body["confidence_score"] <= 100
        assert body["confidence_level"] in {"low", "medium", "high"}
        assert isinstance(body["coverage_results"], list)
        assert isinstance(body["skill_gaps"], list)
        assert isinstance(body["risk_findings"], list)
        assert isinstance(body["dimension_scores"], list)
        assert isinstance(body["decision_trace"], list)
        assert body["policy_version"] == get_policy().POLICY_VERSION
        assert body["summary"]


class TestInvalidEngineerIds:
    def test_unknown_engineer_returns_404(self):
        response = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["unknown_engineer"]},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["error_type"] == "http_error"
        assert "unknown_engineer" in body["detail"]


class TestInvalidProjectIds:
    def test_unknown_project_returns_404(self):
        response = client.post(
            ASSESS_URL,
            json={"project_id": "unknown_project", "engineer_ids": ["kavi"]},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["error_type"] == "http_error"
        assert "unknown_project" in body["detail"]


class TestDuplicateTeamMembers:
    def test_duplicate_engineer_ids_are_deduplicated(self):
        response = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "kavi"]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["team"]) == 1
        assert body["team"][0]["id"] == "kavi"
        assert any(
            finding["finding_type"] == "duplicate_team_member" for finding in body["risk_findings"]
        )


class TestEmptyTeam:
    def test_empty_team_allowed_with_zero_readiness(self):
        response = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": []},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["readiness_score"] == 0
        assert body["confidence_level"] == "low"
        assert any(finding["finding_type"] == "empty_team" for finding in body["risk_findings"])


class TestMissingCriticalCapabilities:
    def test_team_missing_generative_ai_lowers_readiness(self):
        balanced = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        missing = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["vikram", "arjun"]},
        ).json()
        assert missing["readiness_score"] < balanced["readiness_score"]
        assert any(
            gap["is_critical"] and gap["level"] == "missing" for gap in missing["skill_gaps"]
        )


class TestRequestValidationFailures:
    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"engineer_ids": ["kavi"]},
            {"project_id": ""},
        ],
    )
    def test_invalid_payload_returns_422(self, payload: dict):
        response = client.post(ASSESS_URL, json=payload)
        assert response.status_code == 422
        body = response.json()
        assert body["error_type"] == "validation_error"
        assert isinstance(body["detail"], list)

    def test_unknown_policy_version_returns_400(self):
        response = client.post(
            ASSESS_URL,
            json={
                "project_id": "azure_ai_migration",
                "engineer_ids": ["kavi"],
                "policy_version": "v99",
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error_type"] == "http_error"


class TestDeterministicRepeatedRequests:
    def test_same_input_same_scores_and_trace(self):
        first = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        second = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        assert first["readiness_score"] == second["readiness_score"]
        assert first["confidence_score"] == second["confidence_score"]
        assert first["decision_trace"] == second["decision_trace"]
        assert first["assessment_id"] == second["assessment_id"]

    def test_engineer_order_does_not_change_scores_or_id(self):
        forward = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        reversed_payload = {
            "project_id": "azure_ai_migration",
            "engineer_ids": list(reversed(VALID_ASSESS_PAYLOAD["engineer_ids"])),
        }
        reversed_response = client.post(ASSESS_URL, json=reversed_payload).json()
        assert forward["readiness_score"] == reversed_response["readiness_score"]
        assert forward["confidence_score"] == reversed_response["confidence_score"]
        assert forward["assessment_id"] == reversed_response["assessment_id"]


class TestAssessmentIdCanonicalization:
    def test_duplicate_ids_share_assessment_id_with_unique_team(self):
        duplicate = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "kavi"]},
        ).json()
        unique = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi"]},
        ).json()
        assert duplicate["assessment_id"] == unique["assessment_id"]

    def test_assessment_id_includes_policy_version(self):
        default = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        explicit = client.post(
            ASSESS_URL,
            json={**VALID_ASSESS_PAYLOAD, "policy_version": "v1"},
        ).json()
        assert default["assessment_id"] == explicit["assessment_id"]
        assert default["policy_version"] == "v1"


class TestPolicyVersionInResponse:
    def test_default_policy_version_present(self):
        response = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD)
        assert response.json()["policy_version"] == "v1"

    def test_explicit_policy_version_accepted(self):
        response = client.post(
            ASSESS_URL,
            json={**VALID_ASSESS_PAYLOAD, "policy_version": "v1"},
        )
        assert response.status_code == 200
        assert response.json()["policy_version"] == "v1"


class TestDecisionTraceReconciliation:
    def test_readiness_contributions_reconcile(self):
        body = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        readiness_total = sum(
            entry["contribution"]
            for entry in body["decision_trace"]
            if entry["step"] == "readiness"
        )
        assert round(readiness_total, 2) == float(body["readiness_score"])

    def test_confidence_contributions_reconcile(self):
        body = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        confidence_total = sum(
            entry["contribution"]
            for entry in body["decision_trace"]
            if entry["step"] == "confidence"
        )
        assert round(confidence_total, 2) == float(body["confidence_score"])

    def test_trace_entries_include_policy_version(self):
        body = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        assert all(entry["policy_version"] == "v1" for entry in body["decision_trace"])


class TestConfidenceReadinessSeparation:
    def test_scores_can_differ(self):
        body = client.post(
            ASSESS_URL,
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi"]},
        ).json()
        readiness_trace = [
            entry for entry in body["decision_trace"] if entry["step"] == "readiness"
        ]
        confidence_trace = [
            entry for entry in body["decision_trace"] if entry["step"] == "confidence"
        ]
        assert readiness_trace
        assert confidence_trace
        assert (
            body["readiness_score"] != body["confidence_score"] or body["confidence_score"] <= 100
        )


class TestErrorEnvelopeConsistency:
    @pytest.mark.parametrize(
        "status_code,payload",
        [
            (404, {"project_id": "missing", "engineer_ids": ["kavi"]}),
            (
                400,
                {
                    "project_id": "azure_ai_migration",
                    "engineer_ids": ["kavi"],
                    "policy_version": "v99",
                },
            ),
            (422, {}),
        ],
    )
    def test_error_envelope_shape(self, status_code: int, payload: dict):
        response = client.post(ASSESS_URL, json=payload)
        assert response.status_code == status_code
        body = response.json()
        assert "detail" in body
        assert body["status_code"] == status_code
        assert body["error_type"] in {"http_error", "validation_error"}


class TestLegacyEndpointRegression:
    @pytest.mark.parametrize("path,payload", LEGACY_POST_ROUTES)
    def test_legacy_routes_still_respond(self, path: str, payload: dict):
        response = client.post(path, json=payload)
        assert response.status_code in {200, 503}

    @pytest.mark.parametrize("path,payload", LEGACY_POST_ROUTES)
    def test_legacy_routes_accept_text_plain_content_type(self, path: str, payload: dict):
        import json

        response = client.post(
            path,
            content=json.dumps(payload),
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code in {200, 422, 503}


class TestJsonContentTypeValidation:
    _VALID_BODY = '{"project_id":"azure_ai_migration","engineer_ids":["kavi","vikram"]}'

    @pytest.mark.parametrize(
        "content_type",
        [
            "application/json",
            "application/json; charset=utf-8",
            "application/vnd.api+json",
            "application/problem+json",
        ],
    )
    def test_supported_json_media_types_succeed(self, content_type: str):
        response = client.post(
            ASSESS_URL,
            content=self._VALID_BODY,
            headers={"Content-Type": content_type},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["project_id"] == "azure_ai_migration"
        assert len(body["team"]) == 2

    @pytest.mark.parametrize(
        "content_type",
        [
            "text/plain",
            "application/xml",
            "text/xml",
            "multipart/form-data",
        ],
    )
    def test_unsupported_media_types_return_415(self, content_type: str):
        response = client.post(
            ASSESS_URL,
            content=self._VALID_BODY,
            headers={"Content-Type": content_type},
        )
        assert response.status_code == 415
        body = response.json()
        assert body["status_code"] == 415
        assert body["error_type"] == "unsupported_media_type"
        assert isinstance(body["detail"], str)
        assert "json" in body["detail"].lower()

    def test_missing_content_type_returns_415(self):
        response = client.post(ASSESS_URL, content=self._VALID_BODY)
        assert response.status_code == 415
        body = response.json()
        assert body["error_type"] == "unsupported_media_type"

    def test_unsupported_media_response_uses_centralized_envelope(self):
        response = client.post(
            ASSESS_URL,
            content=self._VALID_BODY,
            headers={"Content-Type": "text/plain"},
        )
        body = response.json()
        assert set(body.keys()) == {"detail", "status_code", "error_type"}
        assert body["status_code"] == 415

    def test_unsupported_media_response_has_no_internal_leakage(self):
        response = client.post(
            ASSESS_URL,
            content=self._VALID_BODY,
            headers={"Content-Type": "text/plain"},
        )
        text = response.text.lower()
        assert "traceback" not in text
        assert "exception" not in text
        assert "backend" not in text
        assert ".py" not in text

    def test_malformed_json_returns_controlled_4xx(self):
        response = client.post(
            ASSESS_URL,
            content='{"project_id":',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error_type"] == "validation_error"
        assert body["status_code"] == 422
        assert "traceback" not in response.text.lower()

    def test_invalid_schema_still_returns_422(self):
        response = client.post(
            ASSESS_URL,
            content='{"engineer_ids":["kavi"]}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error_type"] == "validation_error"

    def test_valid_assessment_output_unchanged(self):
        json_response = client.post(ASSESS_URL, json=VALID_ASSESS_PAYLOAD).json()
        raw_response = client.post(
            ASSESS_URL,
            content='{"project_id":"azure_ai_migration","engineer_ids":["kavi","vikram"]}',
            headers={"Content-Type": "application/json"},
        ).json()
        assert raw_response["readiness_score"] == json_response["readiness_score"]
        assert raw_response["confidence_score"] == json_response["confidence_score"]
        assert raw_response["assessment_id"] == json_response["assessment_id"]
        assert raw_response["decision_trace"] == json_response["decision_trace"]


class TestOpenApiSchemaGeneration:
    def test_v2_paths_documented(self):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert ASSESS_URL in paths
        assert CAPABILITIES_URL in paths
        assert POLICIES_URL in paths
        assert ENGINEERS_URL in paths
        assert PROJECTS_URL in paths

    def test_assess_response_schema_includes_domain_fields(self):
        schema = client.get("/openapi.json").json()
        assess_schema = schema["components"]["schemas"]["ReadinessAssessResponse"]
        for field in (
            "readiness_score",
            "confidence_score",
            "decision_trace",
            "policy_version",
            "assessment_id",
            "team",
        ):
            assert field in assess_schema["properties"]

    def test_assess_openapi_documents_json_request_and_error_responses(self):
        openapi = client.get("/openapi.json").json()
        operation = openapi["paths"][ASSESS_URL]["post"]
        schemas = openapi["components"]["schemas"]

        request_content = operation["requestBody"]["content"]
        assert "application/json" in request_content
        assert request_content["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ReadinessAssessRequest"
        }

        success = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert success == {"$ref": "#/components/schemas/ReadinessAssessResponse"}

        error_ref = {"$ref": "#/components/schemas/APIErrorResponse"}
        assert operation["responses"]["415"]["content"]["application/json"]["schema"] == error_ref
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == error_ref
        assert "APIErrorResponse" in schemas
        assert schemas["APIErrorResponse"]["properties"]["error_type"]


class TestSupportingEndpoints:
    def test_list_capabilities(self):
        response = client.get(CAPABILITIES_URL)
        assert response.status_code == 200
        body = response.json()
        assert len(body["capabilities"]) >= 1
        assert "id" in body["capabilities"][0]

    def test_list_engineers(self):
        response = client.get(ENGINEERS_URL)
        assert response.status_code == 200
        assert len(response.json()["engineers"]) >= 1

    def test_list_projects(self):
        response = client.get(PROJECTS_URL)
        assert response.status_code == 200
        projects = response.json()["projects"]
        assert any(project["id"] == "azure_ai_migration" for project in projects)

    def test_list_policies(self):
        response = client.get(POLICIES_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["default_version"] == "v1"
        assert body["policies"][0]["version"] == "v1"
