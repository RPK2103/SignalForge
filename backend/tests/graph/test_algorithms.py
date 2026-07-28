"""Algorithm unit tests for Delivery Graph."""

from datetime import datetime, timezone

from app.domain.graph_enums import GraphEdgeOrigin, GraphEdgeType
from app.domain.graph_models import DeliveryGraphEdge
from app.services.graph.algorithms import (
    Adjacency,
    TraversalBounds,
    blast_radius_traversal,
    bounded_bfs,
    detect_dependency_cycles,
    ownership_concentration_score,
    reachability,
    shortest_path,
)
from app.services.persistence.snapshot_service import snapshot_hash

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _edge(
    eid: str, src: str, tgt: str, etype: GraphEdgeType = GraphEdgeType.DEPENDS_ON
) -> DeliveryGraphEdge:
    return DeliveryGraphEdge(
        tenant_id="tenant-t",
        graph_edge_id=eid,
        source_node_id=src,
        target_node_id=tgt,
        edge_type=etype,
        edge_origin=GraphEdgeOrigin.MANUAL,
        valid_from=NOW,
        first_observed_at=NOW,
        last_observed_at=NOW,
        supporting_dependency_id=f"dep-{eid}",
        payload_hash=snapshot_hash({"id": eid}),
    )


def test_bounded_bfs_and_shortest_path():
    edges = [_edge("e1", "a", "b"), _edge("e2", "b", "c"), _edge("e3", "a", "d")]
    adj = Adjacency.from_edges(edges)
    bounds = TraversalBounds(max_depth=5)
    path, stats = shortest_path(adj, "a", "c", bounds=bounds)
    assert path is not None
    assert path.node_ids == ["a", "b", "c"]
    assert stats.truncated is False


def test_unreachable_nodes():
    adj = Adjacency.from_edges([_edge("e1", "a", "b")])
    path, _ = shortest_path(adj, "a", "z", bounds=TraversalBounds())
    assert path is None


def test_cycle_detection_canonical():
    edges = [
        _edge("e1", "a", "b"),
        _edge("e2", "b", "c"),
        _edge("e3", "c", "a"),
    ]
    cycles, _ = detect_dependency_cycles(edges, bounds=TraversalBounds())
    assert len(cycles) == 1
    assert cycles[0].canonical_key.startswith("a|")
    # Rotated representation must not duplicate.
    cycles2, _ = detect_dependency_cycles(list(reversed(edges)), bounds=TraversalBounds())
    assert cycles2[0].canonical_key == cycles[0].canonical_key


def test_blast_radius_bounds():
    edges = [_edge(f"e{i}", f"n{i}", f"n{i + 1}") for i in range(10)]
    adj = Adjacency.from_edges(edges)
    payload, stats = blast_radius_traversal(
        adj,
        "n0",
        bounds=TraversalBounds(max_depth=3, max_paths=2),
        initiative_node_ids={"n3", "n5"},
        critical_initiative_node_ids={"n3"},
    )
    assert "n1" in payload["directly_affected_node_ids"]
    assert payload["depth_used"] <= 3


def test_reachability_deterministic_order():
    edges = [_edge("e2", "a", "c"), _edge("e1", "a", "b")]
    adj = Adjacency.from_edges(edges)
    reachable, _ = reachability(adj, "a", bounds=TraversalBounds())
    assert reachable == ["b", "c"]


def test_dense_graph_respects_node_budget():
    # Star graph: center -> 100 leaves
    edges = [_edge(f"e{i}", "center", f"leaf{i:03d}") for i in range(100)]
    adj = Adjacency.from_edges(edges)
    distances, _, _, stats = bounded_bfs(
        adj, "center", bounds=TraversalBounds(max_depth=2, max_nodes=20, max_edges=500)
    )
    assert stats.truncated or len(distances) <= 21


def test_ownership_concentration_single_owner():
    score, share, single, low = ownership_concentration_score(primary_count=1, contributor_count=0)
    assert single is True
    assert low is True
    assert score == 1.0
    assert share == 1.0


def test_ownership_concentration_multiple():
    score, share, single, low = ownership_concentration_score(
        primary_count=2, contributor_count=1, primary_allocations=[70, 30]
    )
    assert single is False
    assert share == 0.7
    assert 0 < score <= 1.0


def test_no_recursion_on_cyclic_bfs():
    edges = [_edge("e1", "a", "b"), _edge("e2", "b", "a")]
    adj = Adjacency.from_edges(edges)
    distances, _, _, stats = bounded_bfs(adj, "a", bounds=TraversalBounds(max_depth=10))
    assert set(distances) == {"a", "b"}
    assert stats.operations < 10_000
