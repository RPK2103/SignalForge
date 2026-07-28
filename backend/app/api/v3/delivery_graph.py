"""Delivery Graph v3 read APIs (Phase 3 Prompt 3).

No unrestricted mutation or public rebuild endpoints — the tenant header is
development context, not authentication.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.v3.dependencies import TenantContextDep, get_unit_of_work
from app.db.unit_of_work import UnitOfWork
from app.domain.graph_enums import (
    GraphEdgeType,
    GraphFindingStatus,
    GraphFindingType,
    GraphNodeType,
)
from app.domain.graph_models import (
    BlastRadiusResult,
    DeliveryGraphNode,
    DependencyCycleResult,
    GraphFinding,
    GraphNeighbor,
    GraphPath,
    GraphSummary,
    OwnershipConcentrationResult,
)
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.query_service import DeliveryGraphQueryService

router = APIRouter(prefix="/api/v3/delivery-graph", tags=["Delivery Graph"])

_PAGE = Query(default=20, ge=1, le=100)
_OFFSET = Query(default=0, ge=0)
_DEPTH = Query(default=6, ge=1, le=20)


def _query(uow: UnitOfWork = Depends(get_unit_of_work)) -> DeliveryGraphQueryService:
    return DeliveryGraphQueryService(uow)


def _analysis(uow: UnitOfWork = Depends(get_unit_of_work)) -> GraphAnalysisService:
    return GraphAnalysisService(uow)


@router.get(
    "/summary",
    response_model=GraphSummary,
    summary="Delivery graph summary",
    responses={400: {"description": "Missing tenant context"}},
)
def graph_summary(
    ctx: TenantContextDep,
    active_at: datetime | None = None,
    query: DeliveryGraphQueryService = Depends(_query),
) -> GraphSummary:
    """Tenant-scoped node/edge/finding counts. Graph confidence is rule-based."""
    return query.summary(ctx, active_at=active_at)


@router.get("/nodes", response_model=dict, summary="List graph nodes")
def list_nodes(
    ctx: TenantContextDep,
    node_type: GraphNodeType | None = None,
    active_at: datetime | None = None,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    query: DeliveryGraphQueryService = Depends(_query),
) -> dict:
    page = query.list_nodes(
        ctx, node_type=node_type, active_at=active_at, limit=limit, offset=offset
    )
    return {
        "items": [n.model_dump(mode="json") for n in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get(
    "/nodes/{node_id}",
    response_model=DeliveryGraphNode,
    summary="Get graph node",
    responses={404: {"description": "Not found for tenant"}},
)
def get_node(
    node_id: str,
    ctx: TenantContextDep,
    query: DeliveryGraphQueryService = Depends(_query),
) -> DeliveryGraphNode:
    return query.get_node(ctx, node_id)


@router.get(
    "/nodes/{node_id}/neighbors",
    response_model=list[GraphNeighbor],
    summary="Bounded neighbors",
)
def get_neighbors(
    node_id: str,
    ctx: TenantContextDep,
    direction: str = Query(default="both", pattern="^(incoming|outgoing|both)$"),
    edge_type: list[GraphEdgeType] | None = Query(default=None),
    node_type: list[GraphNodeType] | None = Query(default=None),
    active_at: datetime | None = None,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    query: DeliveryGraphQueryService = Depends(_query),
) -> list[GraphNeighbor]:
    return query.neighbors(
        ctx,
        node_id,
        direction=direction,
        edge_types=edge_type,
        node_types=node_type,
        active_at=active_at,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/paths",
    response_model=list[GraphPath],
    summary="Bounded shortest path",
    responses={422: {"description": "Invalid traversal bounds"}},
)
def get_paths(
    ctx: TenantContextDep,
    source_node_id: str = Query(..., min_length=1, max_length=64),
    target_node_id: str = Query(..., min_length=1, max_length=64),
    max_depth: int = _DEPTH,
    max_paths: int = Query(default=5, ge=1, le=20),
    edge_type: list[GraphEdgeType] | None = Query(default=None),
    active_at: datetime | None = None,
    query: DeliveryGraphQueryService = Depends(_query),
) -> list[GraphPath]:
    return query.shortest_paths(
        ctx,
        source_node_id,
        target_node_id,
        max_depth=max_depth,
        max_paths=max_paths,
        edge_types=edge_type,
        active_at=active_at,
    )


@router.get(
    "/blast-radius",
    response_model=BlastRadiusResult,
    summary="Blast-radius analysis",
)
def get_blast_radius(
    ctx: TenantContextDep,
    origin_node_id: str = Query(..., min_length=1, max_length=64),
    max_depth: int = _DEPTH,
    active_at: datetime | None = None,
    query: DeliveryGraphQueryService = Depends(_query),
) -> BlastRadiusResult:
    return query.blast_radius(ctx, origin_node_id, max_depth=max_depth, active_at=active_at)


@router.get(
    "/dependency-cycles",
    response_model=list[DependencyCycleResult],
    summary="Dependency cycles",
)
def get_dependency_cycles(
    ctx: TenantContextDep,
    max_depth: int = Query(default=10, ge=1, le=20),
    active_at: datetime | None = None,
    query: DeliveryGraphQueryService = Depends(_query),
) -> list[DependencyCycleResult]:
    return query.dependency_cycles(ctx, max_depth=max_depth, active_at=active_at)


@router.get(
    "/ownership-concentration",
    response_model=OwnershipConcentrationResult,
    summary="Ownership concentration",
)
def get_ownership_concentration(
    ctx: TenantContextDep,
    resource_node_id: str = Query(..., min_length=1, max_length=64),
    active_at: datetime | None = None,
    query: DeliveryGraphQueryService = Depends(_query),
) -> OwnershipConcentrationResult:
    return query.ownership_concentration(ctx, resource_node_id, active_at=active_at)


@router.get("/findings", response_model=dict, summary="List graph findings")
def list_findings(
    ctx: TenantContextDep,
    finding_type: GraphFindingType | None = None,
    status: GraphFindingStatus | None = GraphFindingStatus.ACTIVE,
    active_at: datetime | None = None,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict:
    page = uow.graph_findings.list_findings(
        ctx,
        finding_type=finding_type,
        status=status,
        active_at=active_at,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [f.model_dump(mode="json") for f in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get(
    "/findings/{finding_id}",
    response_model=GraphFinding,
    summary="Get graph finding",
    responses={404: {"description": "Not found for tenant"}},
)
def get_finding(
    finding_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> GraphFinding:
    from app.services.enterprise.exceptions import EnterpriseNotFoundError

    finding = uow.graph_findings.get_finding(ctx, finding_id)
    if finding is None:
        raise EnterpriseNotFoundError("Graph finding not found for this tenant")
    return finding


@router.get("/projection-runs", response_model=dict, summary="List projection runs")
def list_projection_runs(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict:
    page = uow.graph_projection_runs.list_runs(ctx, limit=limit, offset=offset)
    return {
        "items": [r.model_dump(mode="json") for r in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/analysis-runs", response_model=dict, summary="List analysis runs")
def list_analysis_runs(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict:
    page = uow.graph_analysis_runs.list_runs(ctx, limit=limit, offset=offset)
    return {
        "items": [r.model_dump(mode="json") for r in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }
