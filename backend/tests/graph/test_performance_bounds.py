"""Performance and bound tests for Delivery Graph algorithms."""

from datetime import datetime, timezone

from app.domain.graph_enums import GraphEdgeOrigin, GraphEdgeType
from app.domain.graph_models import DeliveryGraphEdge
from app.services.graph.algorithms import (
    Adjacency,
    TraversalBounds,
    detect_dependency_cycles,
    reachability,
    shortest_path,
)
from app.services.persistence.snapshot_service import snapshot_hash

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _build_synthetic_graph(n_nodes: int = 500, n_edges: int = 2000):
    edges: list[DeliveryGraphEdge] = []
    # Chain + random-ish deterministic fanout + a cycle component.
    for i in range(min(n_edges, n_nodes - 1)):
        src = f"n{i:04d}"
        tgt = f"n{(i + 1) % n_nodes:04d}"
        edges.append(
            DeliveryGraphEdge(
                tenant_id="synth-graph",
                graph_edge_id=f"e{i:05d}",
                source_node_id=src,
                target_node_id=tgt,
                edge_type=GraphEdgeType.DEPENDS_ON,
                edge_origin=GraphEdgeOrigin.MANUAL,
                valid_from=NOW,
                first_observed_at=NOW,
                last_observed_at=NOW,
                supporting_dependency_id=f"dep{i}",
                payload_hash=snapshot_hash({"i": i}),
            )
        )
    # Extra fan-out from hubs.
    for i in range(n_nodes, n_edges):
        src = f"n{(i * 7) % n_nodes:04d}"
        tgt = f"n{(i * 13) % n_nodes:04d}"
        if src == tgt:
            tgt = f"n{(i * 13 + 1) % n_nodes:04d}"
        edges.append(
            DeliveryGraphEdge(
                tenant_id="synth-graph",
                graph_edge_id=f"e{i:05d}",
                source_node_id=src,
                target_node_id=tgt,
                edge_type=GraphEdgeType.SUPPORTS,
                edge_origin=GraphEdgeOrigin.DERIVED,
                valid_from=NOW,
                first_observed_at=NOW,
                last_observed_at=NOW,
                derivation_rule="synth_fanout",
                derivation_version="1",
                payload_hash=snapshot_hash({"i": i, "fan": True}),
            )
        )
    return edges


def test_synthetic_graph_bounds():
    edges = _build_synthetic_graph(500, 2000)
    assert len(edges) >= 1900
    adj = Adjacency.from_edges(edges)
    bounds = TraversalBounds(max_depth=4, max_nodes=100, max_edges=300, operation_budget=20_000)
    reachable, stats = reachability(adj, "n0000", bounds=bounds)
    assert len(reachable) <= 100
    assert stats.edges_visited <= 300 or stats.truncated
    assert stats.operations <= 20_000 + 1


def test_no_exponential_all_paths():
    edges = _build_synthetic_graph(100, 400)
    adj = Adjacency.from_edges(edges)
    path, stats = shortest_path(
        adj, "n0000", "n0050", bounds=TraversalBounds(max_depth=8, max_paths=5)
    )
    # Single shortest path only — not all paths.
    assert stats.operations < 50_000
    if path:
        assert path.length <= 8


def test_cycle_detection_on_dense_component():
    edges = _build_synthetic_graph(50, 120)
    cycles, stats = detect_dependency_cycles(
        edges, bounds=TraversalBounds(max_depth=20, max_nodes=200, max_edges=500)
    )
    assert isinstance(cycles, list)
    assert stats.operations < 100_000
    # Canonical keys unique
    keys = [c.canonical_key for c in cycles]
    assert len(keys) == len(set(keys))
