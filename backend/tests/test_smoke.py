"""Smoke tests for application import, health routes, and legacy API contracts."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

KAVI_PROFILE = {
    "name": "Kavi",
    "experience": 5,
    "skills": ["Azure", "Python", "Generative AI"],
    "certifications": ["Oracle Generative AI"],
    "projects": ["Azure AI Migration", "LLM Pipeline"],
}

AZURE_AI_PROJECT = {
    "name": "Azure AI Migration",
    "required_skills": ["Azure", "Python", "Generative AI"],
    "description": "Migrate workloads to Azure and deploy generative AI capabilities.",
}

RISK_PROJECT = {
    "name": "Azure AI Migration",
    "required_skills": ["Azure", "Python", "Generative AI"],
    "preferred_skills": ["Generative AI"],
    "domain": "Cloud AI",
}

LEGACY_POST_ROUTES = [
    ("/analyze", KAVI_PROFILE),
    (
        "/project-fit",
        {"engineer": KAVI_PROFILE, "project": AZURE_AI_PROJECT},
    ),
    (
        "/assess-risk",
        {"engineer": KAVI_PROFILE, "project": RISK_PROJECT},
    ),
    (
        "/recommend-team",
        {"project": AZURE_AI_PROJECT, "engineers": [KAVI_PROFILE]},
    ),
    (
        "/generate-insight",
        {
            "engineer_name": "Kavi",
            "project_name": "Azure AI Migration",
            "fit_score": 100,
            "risk_level": "Low",
            "team_coverage": ["Azure", "Python", "Generative AI"],
        },
    ),
    (
        "/simulate",
        {"project_name": "Azure AI Migration", "remove_engineers": ["Kavi"]},
    ),
    (
        "/success-prediction",
        {"project_name": "Azure AI Migration"},
    ),
    (
        "/copilot",
        {
            "project_name": "Azure AI Migration",
            "question": "Why is this project likely to succeed?",
        },
    ),
]


def test_application_import():
    assert app.title == "SignalForge API"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "SignalForge backend is running"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_docs():
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_openapi_lists_legacy_routes():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path, _payload in LEGACY_POST_ROUTES:
        assert path in paths


@pytest.mark.parametrize("path,payload", LEGACY_POST_ROUTES)
def test_legacy_routes_accept_valid_payload(path: str, payload: dict):
    response = client.post(path, json=payload)
    if path == "/generate-insight":
        assert response.status_code == 503
        body = response.json()
        assert body["error_type"] == "http_error"
        assert "Azure OpenAI is not configured" in body["detail"]
        return

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", [path for path, _ in LEGACY_POST_ROUTES])
def test_legacy_routes_reject_empty_body(path: str):
    response = client.post(path, json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error_type"] == "validation_error"
    assert isinstance(body["detail"], list)
