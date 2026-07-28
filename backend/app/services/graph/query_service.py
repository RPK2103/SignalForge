"""Tenant-safe Delivery Graph query service with bounded traversals."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.graph_enums import (
    GRAPH_PROJECTION_VERSION,
    GraphEdgeType,
    GraphFindingStatus,
    GraphNodeType,
)
from app.domain.graph_models import (
    BlastRadiusResult,
    DeliveryGraphNode,
    DependencyCycleResult,
    GraphNeighbor,
    GraphPath,
    GraphSummary,
    OwnershipConcentrationResult,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)
from app.services.graph.algorithms import (
    Adjacency,
    TraversalBounds,
    blast_radius_traversal,
    detect_dependency_cycles,
    ownership_concentration_score,
    reachability,
    shortest_path,
)

logger = logging.getLogger("signalforge.graph.query")

BLAST_EDGE_TYPES = {
    GraphEdgeType.DEPENDS_ON,
    GraphEdgeType.BLOCKS,
    GraphEdgeType.REQUIRES,
    GraphEdgeType.SUPPORTS,
    GraphEdgeType.OWNS,
    GraphEdgeType.CONTRIBUTES_TO,
    GraphEdgeType.MEMBER_OF,
    GraphEdgeType.RESPONDS_TO,
    GraphEdgeType.DEPLOYED_BY,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryGraphQueryService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def summary(self, ctx: TenantContext, *, active_at: datetime | None = None) -> GraphSummary:
        at = active_at or _utcnow()
        nodes_by_type = self._uow.graph_nodes.count_by_type(ctx, active_at=at)
        edges_by_type, edges_by_origin = self._uow.graph_edges.count_by_type_and_origin(
            ctx, active_at=at
        )
        findings_by_type = self._uow.graph_findings.count_by_type(
            ctx, status=GraphFindingStatus.ACTIVE
        )
        latest_proj = self._uow.graph_projection_runs.latest_succeeded(ctx)
        latest_analysis = self._uow.graph_analysis_runs.latest_succeeded(ctx)
        node_count = sum(nodes_by_type.values())
        edge_count = sum(edges_by_type.values())
        return GraphSummary(
            tenant_id=ctx.tenant_id,
            projection_version=GRAPH_PROJECTION_VERSION,
            node_count=node_count,
            edge_count=edge_count,
            active_edge_count=edge_count,
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
            edges_by_origin=edges_by_origin,
            active_finding_count=sum(findings_by_type.values()),
            findings_by_type=findings_by_type,
            latest_projection_run_id=(latest_proj.graph_projection_run_id if latest_proj else None),
            latest_analysis_run_id=(
                latest_analysis.graph_analysis_run_id if latest_analysis else None
            ),
            as_of=at,
        )

    def get_node(self, ctx: TenantContext, node_id: str) -> DeliveryGraphNode:
        node = self._uow.graph_nodes.get_node(ctx, node_id)
        if node is None:
            raise EnterpriseNotFoundError("Graph node not found for this tenant")
        return node

    def list_nodes(
        self,
        ctx: TenantContext,
        *,
        node_type: GraphNodeType | None = None,
        active_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return self._uow.graph_nodes.list_nodes(
            ctx,
            node_type=node_type,
            active_at=active_at,
            limit=limit,
            offset=offset,
        )

    def neighbors(
        self,
        ctx: TenantContext,
        node_id: str,
        *,
        direction: str = "both",
        edge_types: list[GraphEdgeType] | None = None,
        node_types: list[GraphNodeType] | None = None,
        active_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GraphNeighbor]:
        if direction not in {"incoming", "outgoing", "both"}:
            raise EnterpriseValidationError("direction must be incoming|outgoing|both")
        node = self.get_node(ctx, node_id)
        results: list[GraphNeighbor] = []

        def collect(src_filter: str | None, tgt_filter: str | None, dir_label: str) -> None:
            page = self._uow.graph_edges.list_edges(
                ctx,
                source_node_id=src_filter,
                target_node_id=tgt_filter,
                edge_types=edge_types,
                active_at=active_at,
                limit=100,
                offset=0,
            )
            for edge in page.items:
                other_id = edge.target_node_id if dir_label == "outgoing" else edge.source_node_id
                other = self._uow.graph_nodes.get_node(ctx, other_id)
                if other is None:
                    continue
                if node_types and other.node_type not in node_types:
                    continue
                results.append(GraphNeighbor(edge=edge, node=other, direction=dir_label))

        if direction in {"outgoing", "both"}:
            collect(node.graph_node_id, None, "outgoing")
        if direction in {"incoming", "both"}:
            collect(None, node.graph_node_id, "incoming")

        results.sort(key=lambda n: (n.direction, n.edge.edge_type.value, n.edge.graph_edge_id))
        return results[offset : offset + limit]

    def shortest_paths(
        self,
        ctx: TenantContext,
        source_node_id: str,
        target_node_id: str,
        *,
        max_depth: int = 6,
        max_paths: int = 5,
        edge_types: list[GraphEdgeType] | None = None,
        active_at: datetime | None = None,
    ) -> list[GraphPath]:
        self.get_node(ctx, source_node_id)
        self.get_node(ctx, target_node_id)
        bounds = TraversalBounds(max_depth=max_depth, max_paths=max_paths).validated()
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            active_at=active_at,
            edge_types=edge_types,
            max_edges=bounds.max_edges,
        )
        adj = Adjacency.from_edges(edges)
        path, stats = shortest_path(adj, source_node_id, target_node_id, bounds=bounds)
        if stats.truncated:
            logger.info(
                "graph.traversal.rejected tenant_id=%s reason=%s",
                ctx.tenant_id,
                stats.reject_reason,
            )
        if path is None:
            return []
        return [path]

    def reachability(
        self,
        ctx: TenantContext,
        origin_node_id: str,
        *,
        max_depth: int = 6,
        direction: str = "outgoing",
        edge_types: list[GraphEdgeType] | None = None,
        active_at: datetime | None = None,
    ) -> list[str]:
        self.get_node(ctx, origin_node_id)
        bounds = TraversalBounds(max_depth=max_depth).validated()
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            active_at=active_at,
            edge_types=edge_types,
            max_edges=bounds.max_edges,
        )
        adj = Adjacency.from_edges(edges)
        reachable, stats = reachability(adj, origin_node_id, bounds=bounds, direction=direction)
        if stats.truncated:
            logger.info(
                "graph.traversal.rejected tenant_id=%s reason=%s",
                ctx.tenant_id,
                stats.reject_reason,
            )
        return reachable

    def blast_radius(
        self,
        ctx: TenantContext,
        origin_node_id: str,
        *,
        max_depth: int = 6,
        active_at: datetime | None = None,
    ) -> BlastRadiusResult:
        self.get_node(ctx, origin_node_id)
        bounds = TraversalBounds(max_depth=max_depth).validated()
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            active_at=active_at,
            edge_types=list(BLAST_EDGE_TYPES),
            max_edges=bounds.max_edges,
        )
        adj = Adjacency.from_edges(edges)

        initiative_ids: set[str] = set()
        critical_ids: set[str] = set()
        offset = 0
        while True:
            page = self._uow.graph_nodes.list_nodes(
                ctx,
                node_type=GraphNodeType.INITIATIVE,
                active_at=active_at,
                limit=100,
                offset=offset,
            )
            for node in page.items:
                initiative_ids.add(node.graph_node_id)
                # Criticality is on the source entity; approximate via display or
                # look up initiative. Use entity lookup.
                from sqlalchemy import select

                from app.db.models import enterprise as ent_orm

                init = self._uow.session.scalar(
                    select(ent_orm.Initiative).where(
                        ent_orm.Initiative.tenant_id == ctx.tenant_id,
                        ent_orm.Initiative.initiative_id == node.entity_id,
                    )
                )
                if init is not None and init.criticality == "critical":
                    critical_ids.add(node.graph_node_id)
            if offset + 100 >= page.total:
                break
            offset += 100

        payload, stats = blast_radius_traversal(
            adj,
            origin_node_id,
            bounds=bounds,
            initiative_node_ids=initiative_ids,
            critical_initiative_node_ids=critical_ids,
        )
        evidence_ids: list[str] = []
        for edge_id in payload["traversed_edge_ids"]:
            edge = self._uow.graph_edges.get_edge(ctx, edge_id)
            if edge and edge.supporting_evidence_signal_id:
                evidence_ids.append(edge.supporting_evidence_signal_id)
        evidence_ids = sorted(set(evidence_ids))
        if stats.truncated:
            logger.info(
                "graph.traversal.rejected tenant_id=%s reason=%s",
                ctx.tenant_id,
                stats.reject_reason,
            )
        return BlastRadiusResult(
            origin_node_id=origin_node_id,
            supporting_evidence_signal_ids=evidence_ids,
            **payload,
        )

    def dependency_cycles(
        self,
        ctx: TenantContext,
        *,
        max_depth: int = 10,
        active_at: datetime | None = None,
    ) -> list[DependencyCycleResult]:
        bounds = TraversalBounds(max_depth=max_depth, max_nodes=2000, max_edges=5000).validated()
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            active_at=active_at,
            edge_types=[
                GraphEdgeType.DEPENDS_ON,
                GraphEdgeType.BLOCKS,
                GraphEdgeType.REQUIRES,
            ],
            max_edges=bounds.max_edges,
        )
        cycles, stats = detect_dependency_cycles(edges, bounds=bounds)
        if stats.truncated:
            logger.info(
                "graph.traversal.rejected tenant_id=%s reason=%s",
                ctx.tenant_id,
                stats.reject_reason,
            )
        return cycles

    def ownership_concentration(
        self,
        ctx: TenantContext,
        resource_node_id: str,
        *,
        active_at: datetime | None = None,
    ) -> OwnershipConcentrationResult:
        node = self.get_node(ctx, resource_node_id)
        if node.node_type not in {
            GraphNodeType.REPOSITORY,
            GraphNodeType.CAPABILITY,
            GraphNodeType.PROJECT,
        }:
            raise EnterpriseValidationError(
                "ownership concentration applies to repository|capability|project nodes"
            )
        neighbors = self.neighbors(
            ctx,
            resource_node_id,
            direction="incoming",
            edge_types=[
                GraphEdgeType.OWNS,
                GraphEdgeType.CONTRIBUTES_TO,
                GraphEdgeType.SUPPORTS,
            ],
            active_at=active_at,
            limit=100,
            offset=0,
        )
        primary_ids: list[str] = []
        contributor_ids: list[str] = []
        edge_ids: list[str] = []
        evidence_ids: list[str] = []
        allocations: list[int] = []
        warnings = []

        for nb in neighbors:
            edge_ids.append(nb.edge.graph_edge_id)
            if nb.edge.supporting_evidence_signal_id:
                evidence_ids.append(nb.edge.supporting_evidence_signal_id)
            alloc = nb.edge.attributes.get("allocation") if nb.edge.attributes else None
            # For repositories, engineer owners are the concentration signal;
            # team catalog ownership is structural context, not sole-owner risk.
            if (
                node.node_type == GraphNodeType.REPOSITORY
                and nb.node.node_type != GraphNodeType.ENGINEER
                and nb.edge.edge_type == GraphEdgeType.OWNS
            ):
                continue
            if nb.edge.edge_type == GraphEdgeType.OWNS:
                primary_ids.append(nb.node.graph_node_id)
                if isinstance(alloc, int):
                    allocations.append(alloc)
            else:
                contributor_ids.append(nb.node.graph_node_id)

        primary_ids = sorted(set(primary_ids))
        contributor_ids = sorted(set(contributor_ids) - set(primary_ids))
        score, share, single, low = ownership_concentration_score(
            primary_count=len(primary_ids),
            contributor_count=len(contributor_ids),
            primary_allocations=allocations or None,
        )
        from app.domain.graph_enums import GraphDataQualityWarning

        if not primary_ids and not contributor_ids:
            warnings.append(GraphDataQualityWarning.MISSING_OWNER)
        return OwnershipConcentrationResult(
            resource_node_id=resource_node_id,
            resource_node_type=node.node_type,
            active_owner_count=len(primary_ids),
            active_contributor_count=len(contributor_ids),
            primary_owner_node_ids=primary_ids,
            primary_owner_share=share,
            concentration_score=score,
            single_owner=single,
            low_redundancy=low,
            supporting_edge_ids=sorted(set(edge_ids)),
            supporting_evidence_signal_ids=sorted(set(evidence_ids)),
            data_quality_warnings=warnings,
        )
