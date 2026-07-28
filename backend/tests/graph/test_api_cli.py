"""API and CLI tests for Delivery Graph."""

from __future__ import annotations

from app.domain.graph_enums import GraphNodeType

TENANT = {"X-SignalForge-Tenant-ID": "novabank"}


def test_missing_tenant_header(client):
    resp = client.get("/api/v3/delivery-graph/summary")
    assert resp.status_code == 400


def test_foreign_tenant_node_404(client):
    listing = client.get("/api/v3/delivery-graph/nodes?limit=1", headers=TENANT)
    assert listing.status_code == 200
    node_id = listing.json()["items"][0]["graph_node_id"]
    resp = client.get(
        f"/api/v3/delivery-graph/nodes/{node_id}",
        headers={"X-SignalForge-Tenant-ID": "tenant-b"},
    )
    assert resp.status_code == 404


def test_summary_neighbors_paths_blast(client):
    summary = client.get("/api/v3/delivery-graph/summary", headers=TENANT)
    assert summary.status_code == 200
    body = summary.json()
    assert body["node_count"] > 0
    assert body["edge_count"] > 0

    nodes = client.get(
        "/api/v3/delivery-graph/nodes",
        headers=TENANT,
        params={"node_type": "engineer", "limit": 5},
    )
    assert nodes.status_code == 200
    assert nodes.json()["total"] >= 1
    eng = nodes.json()["items"][0]["graph_node_id"]

    neighbors = client.get(
        f"/api/v3/delivery-graph/nodes/{eng}/neighbors",
        headers=TENANT,
        params={"limit": 20},
    )
    assert neighbors.status_code == 200

    teams = client.get(
        "/api/v3/delivery-graph/nodes",
        headers=TENANT,
        params={"node_type": "team", "limit": 1},
    )
    team = teams.json()["items"][0]["graph_node_id"]
    paths = client.get(
        "/api/v3/delivery-graph/paths",
        headers=TENANT,
        params={"source_node_id": eng, "target_node_id": team, "max_depth": 4},
    )
    assert paths.status_code == 200

    blast = client.get(
        "/api/v3/delivery-graph/blast-radius",
        headers=TENANT,
        params={"origin_node_id": eng, "max_depth": 4},
    )
    assert blast.status_code == 200
    assert "directly_affected_node_ids" in blast.json()


def test_cycles_ownership_findings(client):
    cycles = client.get("/api/v3/delivery-graph/dependency-cycles", headers=TENANT)
    assert cycles.status_code == 200
    assert isinstance(cycles.json(), list)
    assert len(cycles.json()) >= 1

    repos = client.get(
        "/api/v3/delivery-graph/nodes",
        headers=TENANT,
        params={"node_type": GraphNodeType.REPOSITORY.value, "limit": 50},
    )
    fraud = next(n for n in repos.json()["items"] if "fraud-scoring" in n["display_label"])
    conc = client.get(
        "/api/v3/delivery-graph/ownership-concentration",
        headers=TENANT,
        params={"resource_node_id": fraud["graph_node_id"]},
    )
    assert conc.status_code == 200
    assert "concentration_score" in conc.json()

    findings = client.get("/api/v3/delivery-graph/findings", headers=TENANT)
    assert findings.status_code == 200
    assert findings.json()["total"] >= 1
    fid = findings.json()["items"][0]["graph_finding_id"]
    one = client.get(f"/api/v3/delivery-graph/findings/{fid}", headers=TENANT)
    assert one.status_code == 200
    assert "calibrated probability" not in one.json()["explanation"].lower()


def test_invalid_depth_bounds(client):
    nodes = client.get(
        "/api/v3/delivery-graph/nodes",
        headers=TENANT,
        params={"limit": 2},
    )
    items = nodes.json()["items"]
    resp = client.get(
        "/api/v3/delivery-graph/paths",
        headers=TENANT,
        params={
            "source_node_id": items[0]["graph_node_id"],
            "target_node_id": items[1]["graph_node_id"],
            "max_depth": 99,
        },
    )
    assert resp.status_code == 422


def test_openapi_includes_delivery_graph(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    assert "/api/v3/delivery-graph/summary" in paths
    assert "/api/v3/delivery-graph/blast-radius" in paths


def test_cli_rebuild_and_summary(projected_novabank, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", projected_novabank)
    from app.core.config import get_settings
    from app.db.session import reset_engine
    from app.graph.cli import main

    get_settings.cache_clear()
    reset_engine()
    assert main(["graph-summary", "--tenant-id", "novabank"]) == 0
    assert main(["graph-validate", "--tenant-id", "novabank"]) == 0
    assert main(["graph-list-findings", "--tenant-id", "novabank", "--limit", "10"]) == 0
    assert main(["graph-analyze", "--tenant-id", "novabank"]) == 0
