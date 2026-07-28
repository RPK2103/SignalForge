"""Tenant-scoped repositories for Delivery Graph projections and findings."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.db.models import graph as orm
from app.domain import graph_models as dm
from app.domain.graph_enums import (
    GraphEdgeType,
    GraphFindingStatus,
    GraphFindingType,
    GraphNodeType,
    GraphProjectionRunState,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    CrossTenantAccessError,
    EnterpriseConflictError,
    EnterpriseNotFoundError,
)

_MAX_PAGE_SIZE = 100
DTO = TypeVar("DTO", bound=BaseModel)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _max_dt(a: datetime, b: datetime) -> datetime:
    return max(_aware(a) or a, _aware(b) or b)


def _to_dto(dto_cls: type[DTO], row: object) -> DTO:
    return dto_cls.model_validate(row, from_attributes=True)


def _dump(model: BaseModel, ctx: TenantContext) -> dict:
    data = model.model_dump()
    data["tenant_id"] = ctx.tenant_id
    for key, value in list(data.items()):
        if hasattr(value, "value"):
            data[key] = value.value
        elif isinstance(value, list) and value and hasattr(value[0], "value"):
            data[key] = [v.value if hasattr(v, "value") else v for v in value]
    for ts_key in ("created_at", "updated_at"):
        if ts_key in data and data[ts_key] is None:
            data.pop(ts_key)
    return data


def _page(dto_cls: type[DTO], rows: Sequence, total: int, limit: int, offset: int) -> dm.Page:  # type: ignore[name-defined]
    from app.domain.enterprise_models import Page

    normalized_limit = max(1, min(limit, _MAX_PAGE_SIZE))
    return Page[dto_cls](
        items=[_to_dto(dto_cls, row) for row in rows],
        total=total,
        limit=normalized_limit,
        offset=max(0, offset),
    )


def _active_edge_clause(model, at: datetime | None):
    """Edge is active at ``at`` when valid_from <= at and (valid_to is null or > at)
    and archived_at is null (or > at for historical).
    """
    point = at or _utcnow()
    return and_(
        model.valid_from <= point,
        or_(model.valid_to.is_(None), model.valid_to > point),
        or_(model.archived_at.is_(None), model.archived_at > point),
    )


def _active_node_clause(model, at: datetime | None):
    point = at or _utcnow()
    return or_(model.archived_at.is_(None), model.archived_at > point)


class _GraphTenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def _insert_guard(self, conflict_message: str):
        try:
            yield
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise EnterpriseConflictError(conflict_message) from exc

    def _tenant_get(self, model, pk_attr: InstrumentedAttribute, pk: str, ctx: TenantContext):
        return self._session.scalar(
            select(model).where(pk_attr == pk, model.tenant_id == ctx.tenant_id)
        )

    def _paginate(
        self,
        query: Select,
        count_query: Select,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence, int]:
        limit = max(1, min(limit, _MAX_PAGE_SIZE))
        offset = max(0, offset)
        total = self._session.scalar(count_query) or 0
        rows = self._session.scalars(query.offset(offset).limit(limit)).all()
        return rows, total

    def _require_same_tenant_node(self, ctx: TenantContext, node_id: str) -> None:
        row = self._tenant_get(
            orm.DeliveryGraphNode, orm.DeliveryGraphNode.graph_node_id, node_id, ctx
        )
        if row is None:
            raise CrossTenantAccessError(
                f"Referenced graph node '{node_id}' is not visible to this tenant"
            )


class GraphNodeRepository(_GraphTenantRepository):
    def upsert_node(
        self, ctx: TenantContext, node: dm.DeliveryGraphNode
    ) -> tuple[dm.DeliveryGraphNode, bool]:
        """Insert or update a node. Returns (node, created)."""
        existing = self._tenant_get(
            orm.DeliveryGraphNode, orm.DeliveryGraphNode.graph_node_id, node.graph_node_id, ctx
        )
        if existing is None:
            # Also check natural key in case of ID mismatch (should not happen).
            by_key = self._session.scalar(
                select(orm.DeliveryGraphNode).where(
                    orm.DeliveryGraphNode.tenant_id == ctx.tenant_id,
                    orm.DeliveryGraphNode.node_type == node.node_type.value,
                    orm.DeliveryGraphNode.entity_id == node.entity_id,
                )
            )
            if by_key is not None:
                existing = by_key
        if existing is None:
            with self._insert_guard("Graph node already exists for this tenant"):
                self._session.add(orm.DeliveryGraphNode(**_dump(node, ctx)))
            return node, True

        existing.display_label = node.display_label
        existing.canonical_key = node.canonical_key
        existing.source_entity_version = node.source_entity_version
        existing.last_observed_at = _aware(node.last_observed_at) or node.last_observed_at
        existing_first = _aware(existing.first_observed_at) or existing.first_observed_at
        node_first = _aware(node.first_observed_at) or node.first_observed_at
        if existing_first > node_first:
            existing.first_observed_at = node_first
        existing.archived_at = node.archived_at
        existing.projection_version = node.projection_version
        existing.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.DeliveryGraphNode, existing), False

    def get_node(self, ctx: TenantContext, graph_node_id: str) -> dm.DeliveryGraphNode | None:
        row = self._tenant_get(
            orm.DeliveryGraphNode, orm.DeliveryGraphNode.graph_node_id, graph_node_id, ctx
        )
        return _to_dto(dm.DeliveryGraphNode, row) if row else None

    def get_by_entity(
        self, ctx: TenantContext, node_type: GraphNodeType, entity_id: str
    ) -> dm.DeliveryGraphNode | None:
        row = self._session.scalar(
            select(orm.DeliveryGraphNode).where(
                orm.DeliveryGraphNode.tenant_id == ctx.tenant_id,
                orm.DeliveryGraphNode.node_type == node_type.value,
                orm.DeliveryGraphNode.entity_id == entity_id,
            )
        )
        return _to_dto(dm.DeliveryGraphNode, row) if row else None

    def list_nodes(
        self,
        ctx: TenantContext,
        *,
        node_type: GraphNodeType | None = None,
        active_at: datetime | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        base = select(orm.DeliveryGraphNode).where(orm.DeliveryGraphNode.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.DeliveryGraphNode)
            .where(orm.DeliveryGraphNode.tenant_id == ctx.tenant_id)
        )
        if node_type is not None:
            base = base.where(orm.DeliveryGraphNode.node_type == node_type.value)
            count = count.where(orm.DeliveryGraphNode.node_type == node_type.value)
        if not include_archived:
            clause = _active_node_clause(orm.DeliveryGraphNode, active_at)
            base = base.where(clause)
            count = count.where(clause)
        rows, total = self._paginate(
            base.order_by(
                orm.DeliveryGraphNode.node_type.asc(),
                orm.DeliveryGraphNode.entity_id.asc(),
            ),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.DeliveryGraphNode, rows, total, limit, offset)

    def list_all_node_ids(self, ctx: TenantContext, *, include_archived: bool = False) -> list[str]:
        query = select(orm.DeliveryGraphNode.graph_node_id).where(
            orm.DeliveryGraphNode.tenant_id == ctx.tenant_id
        )
        if not include_archived:
            query = query.where(orm.DeliveryGraphNode.archived_at.is_(None))
        query = query.order_by(orm.DeliveryGraphNode.graph_node_id.asc())
        return list(self._session.scalars(query).all())

    def archive_node(self, ctx: TenantContext, graph_node_id: str, archived_at: datetime) -> None:
        row = self._tenant_get(
            orm.DeliveryGraphNode, orm.DeliveryGraphNode.graph_node_id, graph_node_id, ctx
        )
        if row is None:
            raise EnterpriseNotFoundError("Graph node not found for this tenant")
        row.archived_at = archived_at
        row.updated_at = _utcnow()
        self._session.flush()

    def count_by_type(
        self, ctx: TenantContext, *, active_at: datetime | None = None
    ) -> dict[str, int]:
        clause = and_(
            orm.DeliveryGraphNode.tenant_id == ctx.tenant_id,
            _active_node_clause(orm.DeliveryGraphNode, active_at),
        )
        rows = self._session.execute(
            select(orm.DeliveryGraphNode.node_type, func.count())
            .where(clause)
            .group_by(orm.DeliveryGraphNode.node_type)
            .order_by(orm.DeliveryGraphNode.node_type.asc())
        ).all()
        return {node_type: count for node_type, count in rows}


class GraphEdgeRepository(_GraphTenantRepository):
    def upsert_edge(
        self, ctx: TenantContext, edge: dm.DeliveryGraphEdge
    ) -> tuple[dm.DeliveryGraphEdge, str]:
        """Insert or refresh an edge.

        Returns (edge, action) where action is created|updated|unchanged.
        """
        self._require_same_tenant_node(ctx, edge.source_node_id)
        self._require_same_tenant_node(ctx, edge.target_node_id)
        if edge.source_node_id == edge.target_node_id:
            raise CrossTenantAccessError("Self-edges are rejected")

        existing = self._tenant_get(
            orm.DeliveryGraphEdge, orm.DeliveryGraphEdge.graph_edge_id, edge.graph_edge_id, ctx
        )
        if existing is None:
            with self._insert_guard("Graph edge already exists for this tenant"):
                self._session.add(orm.DeliveryGraphEdge(**_dump(edge, ctx)))
            return edge, "created"

        changed = (
            existing.payload_hash != edge.payload_hash
            or existing.confidence != edge.confidence
            or existing.criticality != edge.criticality
            or existing.supporting_evidence_signal_id != edge.supporting_evidence_signal_id
            or existing.supporting_ownership_id != edge.supporting_ownership_id
            or existing.supporting_dependency_id != edge.supporting_dependency_id
            or existing.derivation_rule != edge.derivation_rule
            or (existing.valid_to is not None and edge.valid_to is None)
        )
        if not changed and existing.archived_at is None:
            existing.last_observed_at = _max_dt(existing.last_observed_at, edge.last_observed_at)
            existing.updated_at = _utcnow()
            self._session.flush()
            return _to_dto(dm.DeliveryGraphEdge, existing), "unchanged"

        # Temporal closure on material payload change: retain a closed historical
        # snapshot row, then update the stable open edge id in place.
        if existing.payload_hash != edge.payload_hash and existing.valid_to is None:
            from app.domain.enterprise_identifiers import build_entity_id

            closed_at = _aware(edge.valid_from) or edge.valid_from
            prior_from = _aware(existing.valid_from) or existing.valid_from
            hist_id = build_entity_id(
                "gedgehist",
                ctx.tenant_id,
                existing.graph_edge_id,
                prior_from.isoformat(),
                existing.payload_hash[:16],
            )
            prior = self._tenant_get(
                orm.DeliveryGraphEdge, orm.DeliveryGraphEdge.graph_edge_id, hist_id, ctx
            )
            if prior is None:
                self._session.add(
                    orm.DeliveryGraphEdge(
                        graph_edge_id=hist_id,
                        tenant_id=ctx.tenant_id,
                        source_node_id=existing.source_node_id,
                        target_node_id=existing.target_node_id,
                        edge_type=existing.edge_type,
                        edge_origin=existing.edge_origin,
                        confidence=existing.confidence,
                        criticality=existing.criticality,
                        valid_from=existing.valid_from,
                        valid_to=closed_at,
                        first_observed_at=existing.first_observed_at,
                        last_observed_at=existing.last_observed_at,
                        supporting_evidence_signal_id=existing.supporting_evidence_signal_id,
                        supporting_ownership_id=existing.supporting_ownership_id,
                        supporting_dependency_id=existing.supporting_dependency_id,
                        derivation_rule=existing.derivation_rule,
                        derivation_version=existing.derivation_version,
                        attributes=dict(existing.attributes or {}),
                        payload_hash=existing.payload_hash,
                        projection_version=existing.projection_version,
                        archived_at=closed_at,
                    )
                )
                self._session.flush()

            existing.valid_from = edge.valid_from
            existing.valid_to = edge.valid_to
            existing.archived_at = None
            existing.confidence = edge.confidence
            existing.criticality = edge.criticality
            existing.attributes = edge.attributes
            existing.payload_hash = edge.payload_hash
            existing.supporting_evidence_signal_id = edge.supporting_evidence_signal_id
            existing.supporting_ownership_id = edge.supporting_ownership_id
            existing.supporting_dependency_id = edge.supporting_dependency_id
            existing.derivation_rule = edge.derivation_rule
            existing.derivation_version = edge.derivation_version
            existing.edge_origin = edge.edge_origin.value
            existing.edge_type = edge.edge_type.value
            existing.last_observed_at = edge.last_observed_at
            existing.projection_version = edge.projection_version
            existing.updated_at = _utcnow()
            self._session.flush()
            return _to_dto(dm.DeliveryGraphEdge, existing), "updated"

        existing.confidence = edge.confidence
        existing.criticality = edge.criticality
        existing.attributes = edge.attributes
        existing.payload_hash = edge.payload_hash
        existing.supporting_evidence_signal_id = edge.supporting_evidence_signal_id
        existing.supporting_ownership_id = edge.supporting_ownership_id
        existing.supporting_dependency_id = edge.supporting_dependency_id
        existing.derivation_rule = edge.derivation_rule
        existing.derivation_version = edge.derivation_version
        existing.last_observed_at = _max_dt(existing.last_observed_at, edge.last_observed_at)
        existing.valid_to = edge.valid_to
        existing.archived_at = edge.archived_at
        existing.projection_version = edge.projection_version
        existing.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.DeliveryGraphEdge, existing), "updated"

    def get_edge(self, ctx: TenantContext, graph_edge_id: str) -> dm.DeliveryGraphEdge | None:
        row = self._tenant_get(
            orm.DeliveryGraphEdge, orm.DeliveryGraphEdge.graph_edge_id, graph_edge_id, ctx
        )
        return _to_dto(dm.DeliveryGraphEdge, row) if row else None

    def close_edge(
        self, ctx: TenantContext, graph_edge_id: str, closed_at: datetime
    ) -> dm.DeliveryGraphEdge:
        row = self._tenant_get(
            orm.DeliveryGraphEdge, orm.DeliveryGraphEdge.graph_edge_id, graph_edge_id, ctx
        )
        if row is None:
            raise EnterpriseNotFoundError("Graph edge not found for this tenant")
        if row.valid_to is None or row.valid_to > closed_at:
            row.valid_to = closed_at
        row.archived_at = closed_at
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.DeliveryGraphEdge, row)

    def list_edges(
        self,
        ctx: TenantContext,
        *,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
        edge_types: Sequence[GraphEdgeType] | None = None,
        active_at: datetime | None = None,
        include_closed: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        base = select(orm.DeliveryGraphEdge).where(orm.DeliveryGraphEdge.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.DeliveryGraphEdge)
            .where(orm.DeliveryGraphEdge.tenant_id == ctx.tenant_id)
        )
        if source_node_id is not None:
            base = base.where(orm.DeliveryGraphEdge.source_node_id == source_node_id)
            count = count.where(orm.DeliveryGraphEdge.source_node_id == source_node_id)
        if target_node_id is not None:
            base = base.where(orm.DeliveryGraphEdge.target_node_id == target_node_id)
            count = count.where(orm.DeliveryGraphEdge.target_node_id == target_node_id)
        if edge_types:
            values = [e.value for e in edge_types]
            base = base.where(orm.DeliveryGraphEdge.edge_type.in_(values))
            count = count.where(orm.DeliveryGraphEdge.edge_type.in_(values))
        if not include_closed:
            clause = _active_edge_clause(orm.DeliveryGraphEdge, active_at)
            base = base.where(clause)
            count = count.where(clause)
        rows, total = self._paginate(
            base.order_by(
                orm.DeliveryGraphEdge.edge_type.asc(),
                orm.DeliveryGraphEdge.graph_edge_id.asc(),
            ),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.DeliveryGraphEdge, rows, total, limit, offset)

    def list_active_edges_for_traversal(
        self,
        ctx: TenantContext,
        *,
        active_at: datetime | None = None,
        edge_types: Sequence[GraphEdgeType] | None = None,
        max_edges: int = 5000,
    ) -> list[dm.DeliveryGraphEdge]:
        """Bounded load of active edges for in-memory traversal."""
        max_edges = max(1, min(max_edges, 10_000))
        query = select(orm.DeliveryGraphEdge).where(
            orm.DeliveryGraphEdge.tenant_id == ctx.tenant_id,
            _active_edge_clause(orm.DeliveryGraphEdge, active_at),
        )
        if edge_types:
            query = query.where(orm.DeliveryGraphEdge.edge_type.in_([e.value for e in edge_types]))
        query = query.order_by(orm.DeliveryGraphEdge.graph_edge_id.asc()).limit(max_edges)
        rows = self._session.scalars(query).all()
        return [_to_dto(dm.DeliveryGraphEdge, row) for row in rows]

    def list_open_edge_ids(self, ctx: TenantContext) -> list[str]:
        rows = self._session.scalars(
            select(orm.DeliveryGraphEdge.graph_edge_id)
            .where(
                orm.DeliveryGraphEdge.tenant_id == ctx.tenant_id,
                orm.DeliveryGraphEdge.valid_to.is_(None),
                orm.DeliveryGraphEdge.archived_at.is_(None),
            )
            .order_by(orm.DeliveryGraphEdge.graph_edge_id.asc())
        ).all()
        return list(rows)

    def count_by_type_and_origin(
        self, ctx: TenantContext, *, active_at: datetime | None = None
    ) -> tuple[dict[str, int], dict[str, int]]:
        clause = and_(
            orm.DeliveryGraphEdge.tenant_id == ctx.tenant_id,
            _active_edge_clause(orm.DeliveryGraphEdge, active_at),
        )
        by_type = {
            t: c
            for t, c in self._session.execute(
                select(orm.DeliveryGraphEdge.edge_type, func.count())
                .where(clause)
                .group_by(orm.DeliveryGraphEdge.edge_type)
                .order_by(orm.DeliveryGraphEdge.edge_type.asc())
            ).all()
        }
        by_origin = {
            o: c
            for o, c in self._session.execute(
                select(orm.DeliveryGraphEdge.edge_origin, func.count())
                .where(clause)
                .group_by(orm.DeliveryGraphEdge.edge_origin)
                .order_by(orm.DeliveryGraphEdge.edge_origin.asc())
            ).all()
        }
        return by_type, by_origin


class GraphProjectionRunRepository(_GraphTenantRepository):
    def add_run(self, ctx: TenantContext, run: dm.GraphProjectionRun) -> dm.GraphProjectionRun:
        with self._insert_guard("Projection run already exists"):
            self._session.add(orm.GraphProjectionRun(**_dump(run, ctx)))
        return run

    def get_run(self, ctx: TenantContext, run_id: str) -> dm.GraphProjectionRun | None:
        row = self._tenant_get(
            orm.GraphProjectionRun, orm.GraphProjectionRun.graph_projection_run_id, run_id, ctx
        )
        return _to_dto(dm.GraphProjectionRun, row) if row else None

    def update_run(self, ctx: TenantContext, run: dm.GraphProjectionRun) -> dm.GraphProjectionRun:
        row = self._tenant_get(
            orm.GraphProjectionRun,
            orm.GraphProjectionRun.graph_projection_run_id,
            run.graph_projection_run_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Projection run not found for this tenant")
        payload = _dump(run, ctx)
        for key, value in payload.items():
            if key in {"graph_projection_run_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.GraphProjectionRun, row)

    def has_active_full_rebuild(
        self, ctx: TenantContext, *, stale_after_seconds: int = 1800
    ) -> bool:
        """Return True when a durable PENDING/RUNNING full rebuild lock exists.

        Stale RUNNING rows older than ``stale_after_seconds`` are ignored so an
        abandoned lock cannot block rebuilds indefinitely.
        """
        from datetime import timedelta

        cutoff = _utcnow() - timedelta(seconds=max(60, stale_after_seconds))
        row = self._session.scalar(
            select(orm.GraphProjectionRun.graph_projection_run_id).where(
                orm.GraphProjectionRun.tenant_id == ctx.tenant_id,
                orm.GraphProjectionRun.mode == "full_rebuild",
                orm.GraphProjectionRun.state.in_(
                    [
                        GraphProjectionRunState.PENDING.value,
                        GraphProjectionRunState.RUNNING.value,
                    ]
                ),
                or_(
                    orm.GraphProjectionRun.started_at.is_(None),
                    orm.GraphProjectionRun.started_at >= cutoff,
                ),
            )
        )
        return row is not None

    def list_runs(self, ctx: TenantContext, *, limit: int = 20, offset: int = 0):
        base = select(orm.GraphProjectionRun).where(
            orm.GraphProjectionRun.tenant_id == ctx.tenant_id
        )
        count = (
            select(func.count())
            .select_from(orm.GraphProjectionRun)
            .where(orm.GraphProjectionRun.tenant_id == ctx.tenant_id)
        )
        rows, total = self._paginate(
            base.order_by(orm.GraphProjectionRun.created_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.GraphProjectionRun, rows, total, limit, offset)

    def latest_succeeded(self, ctx: TenantContext) -> dm.GraphProjectionRun | None:
        row = self._session.scalar(
            select(orm.GraphProjectionRun)
            .where(
                orm.GraphProjectionRun.tenant_id == ctx.tenant_id,
                orm.GraphProjectionRun.state == GraphProjectionRunState.SUCCEEDED.value,
            )
            .order_by(orm.GraphProjectionRun.completed_at.desc())
            .limit(1)
        )
        return _to_dto(dm.GraphProjectionRun, row) if row else None


class GraphAnalysisRunRepository(_GraphTenantRepository):
    def add_run(self, ctx: TenantContext, run: dm.GraphAnalysisRun) -> dm.GraphAnalysisRun:
        with self._insert_guard("Analysis run already exists"):
            self._session.add(orm.GraphAnalysisRun(**_dump(run, ctx)))
        return run

    def get_run(self, ctx: TenantContext, run_id: str) -> dm.GraphAnalysisRun | None:
        row = self._tenant_get(
            orm.GraphAnalysisRun, orm.GraphAnalysisRun.graph_analysis_run_id, run_id, ctx
        )
        return _to_dto(dm.GraphAnalysisRun, row) if row else None

    def update_run(self, ctx: TenantContext, run: dm.GraphAnalysisRun) -> dm.GraphAnalysisRun:
        row = self._tenant_get(
            orm.GraphAnalysisRun,
            orm.GraphAnalysisRun.graph_analysis_run_id,
            run.graph_analysis_run_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Analysis run not found for this tenant")
        payload = _dump(run, ctx)
        for key, value in payload.items():
            if key in {"graph_analysis_run_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.GraphAnalysisRun, row)

    def list_runs(self, ctx: TenantContext, *, limit: int = 20, offset: int = 0):
        base = select(orm.GraphAnalysisRun).where(orm.GraphAnalysisRun.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.GraphAnalysisRun)
            .where(orm.GraphAnalysisRun.tenant_id == ctx.tenant_id)
        )
        rows, total = self._paginate(
            base.order_by(orm.GraphAnalysisRun.created_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.GraphAnalysisRun, rows, total, limit, offset)

    def latest_succeeded(self, ctx: TenantContext) -> dm.GraphAnalysisRun | None:
        row = self._session.scalar(
            select(orm.GraphAnalysisRun)
            .where(
                orm.GraphAnalysisRun.tenant_id == ctx.tenant_id,
                orm.GraphAnalysisRun.state == "succeeded",
            )
            .order_by(orm.GraphAnalysisRun.completed_at.desc())
            .limit(1)
        )
        return _to_dto(dm.GraphAnalysisRun, row) if row else None


class GraphFindingRepository(_GraphTenantRepository):
    def upsert_active_finding(
        self, ctx: TenantContext, finding: dm.GraphFinding
    ) -> tuple[dm.GraphFinding, str]:
        """Create, observe, or reopen an active finding.

        Returns (finding, created|observed|reopened).
        """
        existing = self._session.scalar(
            select(orm.GraphFinding).where(
                orm.GraphFinding.tenant_id == ctx.tenant_id,
                orm.GraphFinding.finding_hash == finding.finding_hash,
                orm.GraphFinding.status == GraphFindingStatus.ACTIVE.value,
            )
        )
        if existing is not None:
            existing.last_observed_at = _max_dt(existing.last_observed_at, finding.last_observed_at)
            existing.confidence = finding.confidence
            existing.severity = finding.severity.value
            existing.explanation = finding.explanation
            existing.affected_node_ids = finding.affected_node_ids
            existing.supporting_edge_ids = finding.supporting_edge_ids
            existing.supporting_evidence_signal_ids = finding.supporting_evidence_signal_ids
            existing.data_quality_warnings = [
                w.value if hasattr(w, "value") else w for w in finding.data_quality_warnings
            ]
            existing.updated_at = _utcnow()
            self._session.flush()
            return _to_dto(dm.GraphFinding, existing), "observed"

        # Preserve history: do not reuse a resolved row's primary key. Insert a
        # fresh active finding with a time-qualified id when the hash recurs.
        resolved = self._session.scalar(
            select(orm.GraphFinding).where(
                orm.GraphFinding.tenant_id == ctx.tenant_id,
                orm.GraphFinding.finding_hash == finding.finding_hash,
                orm.GraphFinding.status == GraphFindingStatus.RESOLVED.value,
            )
        )
        if resolved is not None:
            from app.domain.enterprise_identifiers import build_entity_id

            finding.graph_finding_id = build_entity_id(
                "gfind",
                ctx.tenant_id,
                finding.finding_hash[:24],
                finding.detected_at.isoformat(),
            )

        with self._insert_guard("Graph finding already exists"):
            self._session.add(orm.GraphFinding(**_dump(finding, ctx)))
        return finding, "created"

    def resolve_finding(
        self, ctx: TenantContext, finding_id: str, resolved_at: datetime
    ) -> dm.GraphFinding:
        row = self._tenant_get(orm.GraphFinding, orm.GraphFinding.graph_finding_id, finding_id, ctx)
        if row is None:
            raise EnterpriseNotFoundError("Graph finding not found for this tenant")
        row.status = GraphFindingStatus.RESOLVED.value
        row.resolved_at = resolved_at
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.GraphFinding, row)

    def get_finding(self, ctx: TenantContext, finding_id: str) -> dm.GraphFinding | None:
        row = self._tenant_get(orm.GraphFinding, orm.GraphFinding.graph_finding_id, finding_id, ctx)
        return _to_dto(dm.GraphFinding, row) if row else None

    def list_findings(
        self,
        ctx: TenantContext,
        *,
        finding_type: GraphFindingType | None = None,
        status: GraphFindingStatus | None = GraphFindingStatus.ACTIVE,
        active_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        base = select(orm.GraphFinding).where(orm.GraphFinding.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.GraphFinding)
            .where(orm.GraphFinding.tenant_id == ctx.tenant_id)
        )
        if finding_type is not None:
            base = base.where(orm.GraphFinding.finding_type == finding_type.value)
            count = count.where(orm.GraphFinding.finding_type == finding_type.value)
        if status is not None:
            base = base.where(orm.GraphFinding.status == status.value)
            count = count.where(orm.GraphFinding.status == status.value)
        if active_at is not None:
            base = base.where(
                orm.GraphFinding.detected_at <= active_at,
                or_(
                    orm.GraphFinding.resolved_at.is_(None),
                    orm.GraphFinding.resolved_at > active_at,
                ),
            )
            count = count.where(
                orm.GraphFinding.detected_at <= active_at,
                or_(
                    orm.GraphFinding.resolved_at.is_(None),
                    orm.GraphFinding.resolved_at > active_at,
                ),
            )
        rows, total = self._paginate(
            base.order_by(
                orm.GraphFinding.finding_type.asc(),
                orm.GraphFinding.graph_finding_id.asc(),
            ),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.GraphFinding, rows, total, limit, offset)

    def list_active_hashes(self, ctx: TenantContext) -> dict[str, str]:
        """Map finding_hash -> graph_finding_id for active findings."""
        rows = self._session.execute(
            select(orm.GraphFinding.finding_hash, orm.GraphFinding.graph_finding_id).where(
                orm.GraphFinding.tenant_id == ctx.tenant_id,
                orm.GraphFinding.status == GraphFindingStatus.ACTIVE.value,
            )
        ).all()
        return {h: fid for h, fid in rows}

    def count_by_type(
        self, ctx: TenantContext, *, status: GraphFindingStatus | None = GraphFindingStatus.ACTIVE
    ) -> dict[str, int]:
        clause = [orm.GraphFinding.tenant_id == ctx.tenant_id]
        if status is not None:
            clause.append(orm.GraphFinding.status == status.value)
        rows = self._session.execute(
            select(orm.GraphFinding.finding_type, func.count())
            .where(and_(*clause))
            .group_by(orm.GraphFinding.finding_type)
            .order_by(orm.GraphFinding.finding_type.asc())
        ).all()
        return {t: c for t, c in rows}

    def add_evidence(
        self, ctx: TenantContext, evidence: dm.GraphFindingEvidence
    ) -> dm.GraphFindingEvidence:
        existing = self._session.scalar(
            select(orm.GraphFindingEvidence).where(
                orm.GraphFindingEvidence.tenant_id == ctx.tenant_id,
                orm.GraphFindingEvidence.graph_finding_id == evidence.graph_finding_id,
                orm.GraphFindingEvidence.evidence_kind == evidence.evidence_kind,
                orm.GraphFindingEvidence.evidence_ref_id == evidence.evidence_ref_id,
            )
        )
        if existing is not None:
            return _to_dto(dm.GraphFindingEvidence, existing)
        with self._insert_guard("Finding evidence already exists"):
            self._session.add(orm.GraphFindingEvidence(**_dump(evidence, ctx)))
        return evidence
