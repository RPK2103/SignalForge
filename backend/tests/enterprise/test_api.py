"""API tests for the v3 enterprise foundation routes."""

from __future__ import annotations

from app.api.v3.dependencies import TENANT_HEADER
from app.api.v3.schemas import MAX_EVIDENCE_PAYLOAD_CHARS

NOVABANK = {TENANT_HEADER: "novabank"}
OTHER = {TENANT_HEADER: "tenant-empty"}


def test_missing_tenant_context_is_rejected(client):
    resp = client.get("/api/v3/organization")
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "tenant_context_error"


def test_invalid_tenant_context_is_rejected(client):
    resp = client.get("/api/v3/organization", headers={TENANT_HEADER: "bad tenant!!"})
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "tenant_context_error"


def test_tenant_a_reads_organization(client):
    resp = client.get("/api/v3/organization", headers=NOVABANK)
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "novabank"
    assert body["slug"] == "novabank"


def test_tenant_b_cannot_read_tenant_a_organization(client):
    # A tenant with no data must get 404 (non-disclosure), not 200 or a leak.
    resp = client.get("/api/v3/organization", headers=OTHER)
    assert resp.status_code == 404
    assert resp.json()["error_type"] == "enterprise_not_found"


def test_demo_summary_counts(client):
    resp = client.get("/api/v3/demo/summary", headers=NOVABANK)
    assert resp.status_code == 200
    counts = resp.json()["counts"]
    assert counts["organizations"] == 1
    assert counts["business_units"] == 2
    assert counts["departments"] == 4
    assert counts["teams"] == 6
    assert counts["engineer_profiles"] == 15
    assert counts["initiatives"] == 5
    assert counts["projects"] == 8
    assert counts["repositories"] == 10
    assert counts["work_items"] == 30
    assert counts["incidents"] == 5
    assert counts["deployments"] == 10
    assert counts["data_sources"] == 3
    assert counts["ingestion_runs"] == 4
    assert counts["evidence_signals"] == 40


def test_demo_summary_is_zero_for_other_tenant(client):
    resp = client.get("/api/v3/demo/summary", headers=OTHER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["organization_id"] is None
    assert all(v == 0 for v in body["counts"].values())


def test_collection_pagination_and_stable_ordering(client):
    page1 = client.get(
        "/api/v3/repositories", headers=NOVABANK, params={"limit": 4, "offset": 0}
    ).json()
    page2 = client.get(
        "/api/v3/repositories", headers=NOVABANK, params={"limit": 4, "offset": 4}
    ).json()
    assert page1["total"] == 10
    assert len(page1["items"]) == 4
    ids1 = [i["repository_id"] for i in page1["items"]]
    ids2 = [i["repository_id"] for i in page2["items"]]
    assert set(ids1).isdisjoint(ids2)
    # Stable ordering across identical calls.
    again = client.get(
        "/api/v3/repositories", headers=NOVABANK, params={"limit": 4, "offset": 0}
    ).json()
    assert [i["repository_id"] for i in again["items"]] == ids1


def test_page_size_bounds_are_enforced(client):
    assert client.get("/api/v3/teams", headers=NOVABANK, params={"limit": 0}).status_code == 422
    assert client.get("/api/v3/teams", headers=NOVABANK, params={"limit": 1000}).status_code == 422


def test_evidence_append_and_dedup_via_api(client):
    sources = client.get("/api/v3/data-sources", headers=NOVABANK).json()
    ds_id = sources["items"][0]["data_source_id"]
    body = {
        "data_source_id": ds_id,
        "source_record_id": "api-rec-1",
        "signal_type": "commit",
        "subject_type": "repository",
        "subject_id": "repo-api-1",
        "event_time": "2026-02-01T09:00:00Z",
        "payload": {"kind": "commit", "sha": "cafebabe"},
    }
    first = client.post("/api/v3/evidence-signals", headers=NOVABANK, json=body)
    assert first.status_code == 200
    assert first.json()["created"] is True
    second = client.post("/api/v3/evidence-signals", headers=NOVABANK, json=body)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert (
        first.json()["signal"]["evidence_signal_id"]
        == second.json()["signal"]["evidence_signal_id"]
    )


def test_evidence_payload_bounds(client):
    sources = client.get("/api/v3/data-sources", headers=NOVABANK).json()
    ds_id = sources["items"][0]["data_source_id"]
    oversized = {"blob": "x" * (MAX_EVIDENCE_PAYLOAD_CHARS + 100)}
    body = {
        "data_source_id": ds_id,
        "source_record_id": "api-rec-big",
        "signal_type": "commit",
        "subject_type": "repository",
        "subject_id": "repo-api-1",
        "event_time": "2026-02-01T09:00:00Z",
        "payload": oversized,
    }
    resp = client.post("/api/v3/evidence-signals", headers=NOVABANK, json=body)
    assert resp.status_code == 422


def test_validation_error_on_bad_enum(client):
    body = {
        "source_type": "not_a_real_source",
        "display_name": "Bad",
    }
    resp = client.post("/api/v3/data-sources", headers=NOVABANK, json=body)
    assert resp.status_code == 422


def test_openapi_includes_v3_routes(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v3/organization" in paths
    assert "/api/v3/evidence-signals" in paths
    assert "/api/v3/demo/summary" in paths


def test_v2_routes_still_present(client):
    schema = client.get("/openapi.json").json()
    v2_paths = [p for p in schema["paths"] if p.startswith("/api/v2")]
    assert v2_paths, "Phase 2 v2 routes must remain registered"
