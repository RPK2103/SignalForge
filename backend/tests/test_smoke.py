"""Smoke tests for application import, health routes, and legacy API contracts.

Under Phase 3 Prompt 7 the backend is default-deny: every route except the
explicit public allowlist (``/``, ``/health`` and — in dev/test — the docs URLs)
requires an authenticated bearer principal, and the legacy root routes are
RBAC-gated at their route entry point. These smoke tests therefore exercise both
the public surface (unauthenticated) and the legacy contracts (authenticated),
plus adversarial 401/403 cases. Resolving the security context opens a DB session,
so a migrated+seeded SQLite database backs the authenticated cases; the legacy
compute itself is unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.seed import seed_database
from app.db.session import get_engine, init_engine, reset_engine
from app.main import app
from tests.support.auth import bearer, broad_tenant_headers, mint_test_token

client = TestClient(app)
auth_client = TestClient(app, headers=broad_tenant_headers())


@pytest.fixture(scope="module")
def _smoke_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    db_path = tmp_path_factory.mktemp("smokedb") / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")

    engine = get_engine(url)
    with Session(engine) as session:
        seed_database(session)
        session.commit()
    engine.dispose()
    return url


@pytest.fixture(autouse=True)
def _use_smoke_db(_smoke_db_url: str) -> Generator[None, None, None]:
    os.environ["DATABASE_URL"] = _smoke_db_url
    get_settings.cache_clear()
    reset_engine()
    init_engine(_smoke_db_url)
    yield
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


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

LEGACY_POST_ROUTES_BY_PATH = {path: payload for path, payload in LEGACY_POST_ROUTES}

# Routes whose required permission the read-only ``executive_reader`` role lacks
# (scenarios.run and chief_of_staff.generate). Used for the 403 adversarial case.
LEGACY_FORBIDDEN_FOR_READER = ["/simulate", "/generate-insight", "/copilot"]


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
    response = auth_client.post(path, json=payload)
    if path == "/generate-insight":
        assert response.status_code == 503
        body = response.json()
        assert body["error_type"] == "http_error"
        assert "Azure OpenAI is not configured" in body["detail"]
        return

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", [path for path, _ in LEGACY_POST_ROUTES])
def test_legacy_routes_reject_empty_body(path: str):
    response = auth_client.post(path, json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error_type"] == "validation_error"
    assert isinstance(body["detail"], list)


@pytest.mark.parametrize("path,payload", LEGACY_POST_ROUTES)
def test_legacy_routes_require_authentication(path: str, payload: dict):
    """Default-deny: every legacy root route rejects an unauthenticated request."""
    response = client.post(path, json=payload)
    assert response.status_code == 401
    body = response.json()
    assert body["error_type"] == "authentication_failed"


@pytest.mark.parametrize("path", LEGACY_FORBIDDEN_FOR_READER)
def test_legacy_routes_forbid_unauthorized_role(path: str):
    """A read-only ``executive_reader`` is denied scenarios.run / chief_of_staff.generate."""
    reader = mint_test_token(subject="reader", roles=("executive_reader",))
    headers = dict(bearer(reader))
    headers["X-SignalForge-Tenant-ID"] = "novabank"
    payload = dict(LEGACY_POST_ROUTES_BY_PATH[path])
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 403
