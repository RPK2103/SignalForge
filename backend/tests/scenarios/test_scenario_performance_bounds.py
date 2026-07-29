"""Bounded large-graph overlay harness (500 nodes / 2000 edges)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.unit_of_work import UnitOfWork
from app.domain.graph_enums import GraphEdgeOrigin, GraphEdgeType, GraphNodeType
from app.domain.graph_models import DeliveryGraphEdge, DeliveryGraphNode
from app.domain.prediction_enums import EstimateKind
from app.domain.scenario_constants import (
    MAX_COMPARISON_RUNS,
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_IMPACTS_PER_RESULT,
    MAX_RETURNED_PATHS,
    MAX_SCENARIO_CHANGES,
    MAX_SUBJECT_IDS_PER_CHANGE,
    MAX_WATCHES_PER_EVALUATION_BATCH,
)
from app.domain.scenario_enums import EstimateComparability
from app.domain.tenant_context import TenantContext
from app.services.graph.algorithms import Adjacency, TraversalBounds, blast_radius_traversal
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.scenarios.graph_overlay import ScenarioGraphOverlayEngine
from app.services.scenarios.impacts import build_impacts
from app.services.scenarios.prediction_adapter import ScenarioEstimate, ScenarioPredictionPair

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _seed_large_graph(
    uow: UnitOfWork, ctx: TenantContext, *, nodes: int = 500, edges: int = 2000
) -> str:
    """Create a cyclic, multi-component, high-degree synthetic graph in ORM tables."""
    created_nodes: list[str] = []
    for i in range(nodes):
        if i == 0:
            ntype = GraphNodeType.PROJECT
            entity_id = "proj_perf_seed"
        elif i % 17 == 0:
            ntype = GraphNodeType.INITIATIVE
            entity_id = f"init_perf_{i}"
        elif i % 11 == 0:
            ntype = GraphNodeType.REPOSITORY
            entity_id = f"repo_perf_{i}"
        elif i % 7 == 0:
            ntype = GraphNodeType.ENGINEER
            entity_id = f"eng_perf_{i}"
        else:
            ntype = GraphNodeType.TEAM
            entity_id = f"team_perf_{i}"
        node_id = f"gn_perf_{i:04d}"
        node = DeliveryGraphNode(
            tenant_id=ctx.tenant_id,
            graph_node_id=node_id,
            node_type=ntype,
            entity_id=entity_id,
            canonical_key=f"{ntype.value}:{entity_id}",
            display_label=f"perf-{i}",
            first_observed_at=AS_OF,
            last_observed_at=AS_OF,
        )
        uow.graph_nodes.upsert_node(ctx, node)
        created_nodes.append(node_id)

    edge_i = 0

    def _add_edge(src: str, dst: str, etype: GraphEdgeType) -> None:
        nonlocal edge_i
        if edge_i >= edges or src == dst:
            return
        payload = {"i": edge_i, "src": src, "dst": dst, "t": etype.value}
        uow.graph_edges.upsert_edge(
            ctx,
            DeliveryGraphEdge(
                tenant_id=ctx.tenant_id,
                graph_edge_id=f"ge_perf_{edge_i:05d}",
                source_node_id=src,
                target_node_id=dst,
                edge_type=etype,
                edge_origin=GraphEdgeOrigin.MANUAL,
                valid_from=AS_OF,
                valid_to=None,
                first_observed_at=AS_OF,
                last_observed_at=AS_OF,
                attributes={},
                payload_hash=snapshot_hash(payload),
            ),
        )
        edge_i += 1

    for i in range(1, nodes):
        src = created_nodes[0] if i % 5 != 0 else created_nodes[i - 1]
        _add_edge(src, created_nodes[i], GraphEdgeType.DEPENDS_ON)

    for i in range(0, min(40, nodes - 1)):
        _add_edge(created_nodes[i], created_nodes[(i + 3) % 40], GraphEdgeType.DEPENDS_ON)

    island_start = max(nodes - 50, 100)
    while edge_i < edges:
        a = created_nodes[edge_i % nodes]
        b = created_nodes[(edge_i * 7 + 13) % nodes]
        if edge_i % 11 == 0:
            a = created_nodes[island_start + (edge_i % 40)]
            b = created_nodes[island_start + ((edge_i + 1) % 40)]
        _add_edge(a, b, GraphEdgeType.SUPPORTS)

    uow.session.flush()
    return created_nodes[0]


def test_large_graph_overlay_respects_budgets(db_session: Session, tenant_a: TenantContext):
    uow = UnitOfWork(db_session)
    seed_node = _seed_large_graph(uow, tenant_a, nodes=500, edges=2000)
    uow.commit()

    node_page = uow.graph_nodes.list_nodes(tenant_a, limit=1, offset=0, active_at=AS_OF)
    edge_page = uow.graph_edges.list_edges(tenant_a, limit=1, offset=0, active_at=AS_OF)
    assert node_page.total >= 500
    assert edge_page.total >= 2000

    query_count = {"n": 0}
    original_execute = uow.session.execute

    def counting_execute(*args, **kwargs):
        query_count["n"] += 1
        return original_execute(*args, **kwargs)

    uow.session.execute = counting_execute  # type: ignore[method-assign]

    engine = ScenarioGraphOverlayEngine(uow)
    overlay = engine.apply(
        tenant_a,
        target_type="project",
        target_id="proj_perf_seed",
        as_of_at=AS_OF,
        assumptions={
            "schema_version": "scenario_assumptions_v1",
            "kind": "combined",
            "changes": [
                {
                    "kind": "engineer_unavailable",
                    "engineer_id": "eng_perf_7",
                    "unavailable_from": AS_OF.isoformat(),
                    "unavailable_until": AS_OF.isoformat(),
                },
                {
                    "kind": "repository_unavailable",
                    "repository_id": "repo_perf_11",
                    "unavailable_from": AS_OF.isoformat(),
                    "unavailable_until": AS_OF.isoformat(),
                },
            ],
        },
        baseline_finding_summaries=[],
    )

    assert overlay.nodes_examined <= MAX_GRAPH_NODES
    assert overlay.edges_examined <= MAX_GRAPH_EDGES
    assert len(overlay.path_explanations) <= MAX_RETURNED_PATHS
    assert overlay.blast_radius_node_count <= MAX_GRAPH_NODES
    assert query_count["n"] < 800, f"query_count={query_count['n']}"

    edges = uow.graph_edges.list_active_edges_for_traversal(
        tenant_a, active_at=AS_OF, max_edges=MAX_GRAPH_EDGES
    )
    adj = Adjacency.from_edges(list(edges)[:MAX_GRAPH_EDGES])
    bounds = TraversalBounds(
        max_depth=MAX_GRAPH_DEPTH,
        max_nodes=MAX_GRAPH_NODES,
        max_edges=MAX_GRAPH_EDGES,
        max_paths=MAX_RETURNED_PATHS,
    ).validated()
    initiative_node_ids = {
        n.graph_node_id
        for n in uow.graph_nodes.list_nodes(tenant_a, limit=500, offset=0, active_at=AS_OF).items
        if (n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type))
        == "initiative"
    }
    radius, stats = blast_radius_traversal(
        adj,
        seed_node,
        bounds=bounds,
        initiative_node_ids=initiative_node_ids,
        critical_initiative_node_ids=set(),
    )
    assert stats.nodes_visited <= MAX_GRAPH_NODES
    assert stats.edges_visited <= MAX_GRAPH_EDGES
    assert len(radius.get("path_explanations") or []) <= MAX_RETURNED_PATHS

    pair = ScenarioPredictionPair(
        baseline=ScenarioEstimate(estimate_kind=EstimateKind.UNCALIBRATED_SCORE, risk_score=40.0),
        simulated=ScenarioEstimate(estimate_kind=EstimateKind.UNCALIBRATED_SCORE, risk_score=55.0),
        estimate_comparability=EstimateComparability.COMPARABLE_SCORE,
        probability_delta=None,
        risk_score_delta=15.0,
    )
    impacts = build_impacts(
        tenant_a,
        scenario_run_id="srun_perf_bounds",
        graph_overlay=overlay,
        prediction_pair=pair,
    )
    assert len(impacts) <= MAX_IMPACTS_PER_RESULT


def test_comparison_and_watch_batch_limits():
    assert MAX_WATCHES_PER_EVALUATION_BATCH == 100
    assert MAX_COMPARISON_RUNS == 20
    assert MAX_SCENARIO_CHANGES == 10
    assert MAX_SUBJECT_IDS_PER_CHANGE == 50
