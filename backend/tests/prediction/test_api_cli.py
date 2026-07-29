"""API and CLI tests for Delivery Prediction."""

from __future__ import annotations

from app.domain.enterprise_identifiers import build_entity_id

TENANT = {"X-SignalForge-Tenant-ID": "novabank"}


def _project_id() -> str:
    return build_entity_id("proj", "novabank", "rt-payments-rail")


def test_missing_tenant_header(client):
    resp = client.get("/api/v3/predictions/data-health")
    assert resp.status_code == 400


def test_data_health_and_outcomes(client):
    health = client.get("/api/v3/predictions/data-health", headers=TENANT)
    assert health.status_code == 200
    body = health.json()
    assert body["tenant_id"] == "novabank"
    assert body["labeled_outcomes"] >= 60

    outcomes = client.get("/api/v3/predictions/outcomes", headers=TENANT)
    assert outcomes.status_code == 200
    assert outcomes.json()["total"] >= 60


def test_project_predict_route(client):
    project_id = _project_id()
    resp = client.get(
        f"/api/v3/predictions/projects/{project_id}",
        headers=TENANT,
        params={"horizon_days": 90, "as_of": "2025-06-01T00:00:00Z"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "prediction" in body
    assert body["prediction"]["target_id"] == project_id
    assert body["prediction"]["estimate_kind"] in {
        "uncalibrated_score",
        "calibrated_probability",
        "insufficient_data",
    }

    history = client.get(
        f"/api/v3/predictions/projects/{project_id}/history",
        headers=TENANT,
    )
    assert history.status_code == 200
    assert history.json()["total"] >= 1


def test_unsupported_horizon_422(client):
    project_id = _project_id()
    resp = client.get(
        f"/api/v3/predictions/projects/{project_id}",
        headers=TENANT,
        params={"horizon_days": 45},
    )
    assert resp.status_code == 422


def test_models_and_runs_routes(client):
    models = client.get("/api/v3/predictions/models", headers=TENANT)
    assert models.status_code == 200
    assert "items" in models.json()

    runs = client.get("/api/v3/predictions/runs", headers=TENANT)
    assert runs.status_code == 200

    evaluations = client.get("/api/v3/predictions/evaluations", headers=TENANT)
    assert evaluations.status_code == 200


def test_openapi_includes_predictions(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    assert "/api/v3/predictions/data-health" in paths
    assert "/api/v3/predictions/projects/{project_id}" in paths
    assert "/api/v3/predictions/models" in paths


def test_cli_help_and_data_health(projected_novabank, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", projected_novabank)
    from app.core.config import get_settings
    from app.db.session import reset_engine
    from app.prediction.cli import build_parser, main

    get_settings.cache_clear()
    reset_engine()

    parser = build_parser()
    help_text = parser.format_help()
    assert "data-health" in help_text
    assert "list-models" in help_text
    assert "promote" in help_text

    assert main(["data-health", "--tenant-id", "novabank"]) == 0
    assert main(["list-models", "--tenant-id", "novabank", "--limit", "10"]) == 0
    assert main(["validate", "--tenant-id", "novabank"]) == 0
