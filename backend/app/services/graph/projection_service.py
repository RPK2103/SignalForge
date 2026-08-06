"""Deterministic Delivery Graph projection from enterprise/connector sources.

Source-of-truth tables remain authoritative. Projection is tenant-scoped,
idempotent, rebuildable, and does not drop graph tables during rebuild.
Failures leave the prior valid graph intact (transaction rollback).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import enterprise as ent_orm
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.graph_enums import (
    GRAPH_DERIVATION_VERSION,
    GRAPH_PROJECTION_VERSION,
    GraphEdgeOrigin,
    GraphEdgeType,
    GraphNodeType,
    GraphProjectionMode,
    GraphProjectionRunState,
)
from app.domain.graph_models import DeliveryGraphEdge, DeliveryGraphNode, GraphProjectionRun
from app.domain.tenant_context import TenantContext
from app.observability.domain import record_graph_rebuild
from app.security.rls import set_transaction_tenant
from app.services.enterprise.exceptions import EnterpriseConflictError, EnterpriseValidationError
from app.services.graph.confidence import edge_confidence
from app.services.persistence.snapshot_service import snapshot_hash

logger = logging.getLogger("signalforge.graph.projection")

MAX_SUBJECT_IDS = 50
INCREMENTAL_OVERLAP = timedelta(minutes=5)

# Map a graph run state to the bounded telemetry outcome vocabulary. Only a clean
# rebuild is "success"; a truncated/partial run is degraded, not a full failure.
_RUN_STATE_OUTCOME: dict[GraphProjectionRunState, str] = {
    GraphProjectionRunState.SUCCEEDED: "success",
    GraphProjectionRunState.PARTIAL: "partial",
    GraphProjectionRunState.FAILED: "failure",
}

# Map ownership types to graph edge types.
_OWNERSHIP_EDGE: dict[str, GraphEdgeType] = {
    "primary": GraphEdgeType.OWNS,
    "secondary": GraphEdgeType.SUPPORTS,
    "contributor": GraphEdgeType.CONTRIBUTES_TO,
    "supporting": GraphEdgeType.SUPPORTS,
}

_DEPENDENCY_EDGE: dict[str, GraphEdgeType] = {
    "depends_on": GraphEdgeType.DEPENDS_ON,
    "blocks": GraphEdgeType.BLOCKS,
    "shares_capability": GraphEdgeType.SUPPORTS,
    "integrates_with": GraphEdgeType.DEPENDS_ON,
    "owned_by": GraphEdgeType.OWNS,
}

_ENTITY_TO_NODE: dict[str, GraphNodeType] = {
    "organization": GraphNodeType.ORGANIZATION,
    "business_unit": GraphNodeType.BUSINESS_UNIT,
    "department": GraphNodeType.DEPARTMENT,
    "team": GraphNodeType.TEAM,
    "engineer_profile": GraphNodeType.ENGINEER,
    "initiative": GraphNodeType.INITIATIVE,
    "project": GraphNodeType.PROJECT,
    "capability": GraphNodeType.CAPABILITY,
    "skill": GraphNodeType.SKILL,
    "repository": GraphNodeType.REPOSITORY,
    "work_item": GraphNodeType.WORK_ITEM,
    "pull_request": GraphNodeType.PULL_REQUEST,
    "sprint": GraphNodeType.SPRINT,
    "incident": GraphNodeType.INCIDENT,
    "deployment": GraphNodeType.DEPLOYMENT,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = (end - start).total_seconds() * 1000.0
    return delta if delta >= 0 else None


def _label(value: str | None, fallback: str) -> str:
    text = (value or fallback).strip()
    return text[:128] if text else fallback[:128]


def graph_node_id(tenant_id: str, node_type: GraphNodeType, entity_id: str) -> str:
    return build_entity_id("gnode", tenant_id, node_type.value, entity_id)


def graph_edge_id(
    tenant_id: str,
    source_node_id: str,
    target_node_id: str,
    edge_type: GraphEdgeType,
    *natural: str,
) -> str:
    return build_entity_id(
        "gedge", tenant_id, source_node_id, target_node_id, edge_type.value, *natural
    )


def projection_run_id(tenant_id: str, mode: str, started_at: datetime) -> str:
    return build_entity_id("gprun", tenant_id, mode, started_at.isoformat())


class GraphProjectionService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def full_rebuild(self, ctx: TenantContext) -> GraphProjectionRun:
        if self._uow.graph_projection_runs.has_active_full_rebuild(ctx):
            logger.info(
                "graph.projection.conflict tenant_id=%s reason=active_full_rebuild",
                ctx.tenant_id,
            )
            raise EnterpriseConflictError("A full graph rebuild is already running for this tenant")
        return self._project(ctx, mode=GraphProjectionMode.FULL_REBUILD, durable_lock=True)

    def incremental_refresh(
        self, ctx: TenantContext, *, since: datetime | None = None
    ) -> GraphProjectionRun:
        latest = self._uow.graph_projection_runs.latest_succeeded(ctx)
        watermark = since
        if watermark is None and latest is not None:
            watermark = latest.source_high_watermark
        if watermark is not None:
            watermark = watermark - INCREMENTAL_OVERLAP
        return self._project(ctx, mode=GraphProjectionMode.INCREMENTAL, since=watermark)

    def subject_refresh(self, ctx: TenantContext, subject_ids: list[str]) -> GraphProjectionRun:
        cleaned = sorted({s.strip() for s in subject_ids if s and s.strip()})
        if not cleaned:
            raise EnterpriseValidationError("subject_ids must be non-empty")
        if len(cleaned) > MAX_SUBJECT_IDS:
            raise EnterpriseValidationError(f"subject_ids exceed bound of {MAX_SUBJECT_IDS}")
        return self._project(ctx, mode=GraphProjectionMode.SUBJECT_REFRESH, subject_ids=cleaned)

    def _project(
        self,
        ctx: TenantContext,
        *,
        mode: GraphProjectionMode,
        since: datetime | None = None,
        subject_ids: list[str] | None = None,
        durable_lock: bool = False,
    ) -> GraphProjectionRun:
        started = _utcnow()
        run = GraphProjectionRun(
            tenant_id=ctx.tenant_id,
            graph_projection_run_id=projection_run_id(ctx.tenant_id, mode.value, started),
            mode=mode,
            projection_version=GRAPH_PROJECTION_VERSION,
            state=GraphProjectionRunState.RUNNING,
            started_at=started,
            subject_ids=subject_ids or [],
        )
        self._uow.graph_projection_runs.add_run(ctx, run)
        self._uow.session.flush()
        # Commit the RUNNING lock so concurrent sessions observe the mutex.
        # Graph mutations remain uncommitted until the caller commits success.
        if durable_lock:
            self._uow.session.commit()
            # Commit ends the prior transaction-local RLS GUC; restore it so
            # subsequent node/edge writes and update_run remain tenant-visible.
            set_transaction_tenant(self._uow.session, ctx.tenant_id)
        logger.info(
            "graph.projection.started tenant_id=%s run_id=%s mode=%s projection_version=%s",
            ctx.tenant_id,
            run.graph_projection_run_id,
            mode.value,
            GRAPH_PROJECTION_VERSION,
        )

        errors: list[str] = []
        hwm_samples: list[datetime] = []
        telemetry_emitted = False
        try:
            # Nodes are always fully projected so edge endpoints resolve.
            # Incremental ``since`` filters edge source rows only.
            node_index, node_counts = self._project_nodes(
                ctx, since=None, subject_ids=None, hwm_samples=hwm_samples
            )
            edge_since = since if mode == GraphProjectionMode.INCREMENTAL else None
            edge_counts, desired_edge_ids = self._project_edges(
                ctx,
                node_index,
                since=edge_since,
                subject_ids=subject_ids,
                hwm_samples=hwm_samples,
            )
            closed = 0
            if mode == GraphProjectionMode.FULL_REBUILD:
                closed = self._close_obsolete_edges(ctx, desired_edge_ids, started)
                archived = self._archive_orphan_nodes(ctx, set(node_index.values()), started)
            else:
                archived = 0

            run.nodes_examined = node_counts["examined"]
            run.nodes_created = node_counts["created"]
            run.nodes_updated = node_counts["updated"]
            run.nodes_archived = archived
            run.edges_examined = edge_counts["examined"]
            run.edges_created = edge_counts["created"]
            run.edges_updated = edge_counts["updated"]
            run.edges_closed = closed + edge_counts.get("closed", 0)
            run.source_high_watermark = max(hwm_samples) if hwm_samples else started
            run.state = (
                GraphProjectionRunState.PARTIAL if errors else GraphProjectionRunState.SUCCEEDED
            )
            run.completed_at = _utcnow()
            run.errors = errors
            run.sanitized_error_summary = "; ".join(errors)[:1024] if errors else None
            self._uow.graph_projection_runs.update_run(ctx, run)
            self._uow.session.flush()
            logger.info(
                "graph.projection.completed tenant_id=%s run_id=%s state=%s "
                "nodes_created=%s edges_created=%s edges_closed=%s",
                ctx.tenant_id,
                run.graph_projection_run_id,
                run.state.value,
                run.nodes_created,
                run.edges_created,
                run.edges_closed,
            )
            # Defer success/partial telemetry until the enclosing UoW commits so a
            # later rollback never reports committed success. Failures emit now.
            outcome = _RUN_STATE_OUTCOME.get(run.state, "failure")
            duration = _duration_ms(started, run.completed_at)
            incremental = mode != GraphProjectionMode.FULL_REBUILD
            self._uow.note_pending_telemetry(
                lambda o=outcome, d=duration, i=incremental: record_graph_rebuild(
                    outcome=o, duration_ms=d, incremental=i
                )
            )
            telemetry_emitted = True
            return run
        except Exception as exc:
            if not telemetry_emitted:
                self._uow.session.rollback()
                set_transaction_tenant(self._uow.session, ctx.tenant_id)
                self._record_failed_run(ctx, run, mode, started, subject_ids or [], exc)
                record_graph_rebuild(
                    outcome="failure",
                    duration_ms=_duration_ms(started, _utcnow()),
                    incremental=mode != GraphProjectionMode.FULL_REBUILD,
                )
                logger.info(
                    "graph.projection.failed tenant_id=%s mode=%s error_type=%s",
                    ctx.tenant_id,
                    mode.value,
                    type(exc).__name__,
                )
            raise

    def _record_failed_run(
        self,
        ctx: TenantContext,
        run: GraphProjectionRun,
        mode: GraphProjectionMode,
        started: datetime,
        subject_ids: list[str],
        exc: Exception,
    ) -> None:
        """Persist a FAILED run without leaving a half-built active graph."""
        failed = GraphProjectionRun(
            tenant_id=ctx.tenant_id,
            graph_projection_run_id=run.graph_projection_run_id,
            mode=mode,
            projection_version=GRAPH_PROJECTION_VERSION,
            state=GraphProjectionRunState.FAILED,
            started_at=started,
            completed_at=_utcnow(),
            subject_ids=subject_ids,
            sanitized_error_summary=type(exc).__name__[:1024],
            errors=[type(exc).__name__],
        )
        try:
            set_transaction_tenant(self._uow.session, ctx.tenant_id)
            existing = self._uow.graph_projection_runs.get_run(ctx, run.graph_projection_run_id)
            if existing is None:
                self._uow.graph_projection_runs.add_run(ctx, failed)
            else:
                self._uow.graph_projection_runs.update_run(ctx, failed)
            self._uow.session.commit()
        except Exception:
            self._uow.session.rollback()

    # ------------------------------------------------------------------ nodes
    def _project_nodes(
        self,
        ctx: TenantContext,
        *,
        since: datetime | None,
        subject_ids: list[str] | None,
        hwm_samples: list[datetime] | None = None,
    ) -> tuple[dict[tuple[GraphNodeType, str], str], dict[str, int]]:
        """Returns mapping (node_type, entity_id) -> graph_node_id and counts."""
        index: dict[tuple[GraphNodeType, str], str] = {}
        counts = {"examined": 0, "created": 0, "updated": 0}
        now = _utcnow()
        _ = subject_ids  # nodes always fully projected for endpoint integrity
        sources = [
            (
                GraphNodeType.ORGANIZATION,
                self._rows(ent_orm.Organization, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.organization_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.BUSINESS_UNIT,
                self._rows(ent_orm.BusinessUnit, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.business_unit_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.DEPARTMENT,
                self._rows(ent_orm.Department, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.department_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.TEAM,
                self._rows(ent_orm.Team, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.team_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.ENGINEER,
                self._rows(ent_orm.EngineerProfile, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.engineer_profile_id, r.display_name, r.archived_at),
            ),
            (
                GraphNodeType.INITIATIVE,
                self._rows(ent_orm.Initiative, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.initiative_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.PROJECT,
                self._rows(ent_orm.EnterpriseProject, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.enterprise_project_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.CAPABILITY,
                self._rows(ent_orm.EnterpriseCapability, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.capability_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.SKILL,
                self._rows(ent_orm.EnterpriseSkill, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.skill_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.REPOSITORY,
                self._rows(ent_orm.Repository, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.repository_id, r.name, r.archived_at),
            ),
            (
                GraphNodeType.PULL_REQUEST,
                self._rows(ent_orm.PullRequest, ctx, since, hwm_samples=hwm_samples),
                lambda r: (
                    r.pull_request_id,
                    f"PR#{r.number} {r.title}"[:128],
                    r.archived_at,
                ),
            ),
            (
                GraphNodeType.WORK_ITEM,
                self._rows(ent_orm.WorkItem, ctx, since, hwm_samples=hwm_samples),
                lambda r: (
                    r.work_item_id,
                    (r.title or r.external_reference)[:128],
                    None,
                ),
            ),
            (
                GraphNodeType.SPRINT,
                self._rows(ent_orm.Sprint, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.sprint_id, r.name, None),
            ),
            (
                GraphNodeType.INCIDENT,
                self._rows(ent_orm.Incident, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.incident_id, r.external_reference, None),
            ),
            (
                GraphNodeType.DEPLOYMENT,
                self._rows(ent_orm.Deployment, ctx, since, hwm_samples=hwm_samples),
                lambda r: (r.deployment_id, r.external_reference, None),
            ),
        ]

        for node_type, rows, extractor in sources:
            for row in rows:
                entity_id, label, archived_at = extractor(row)
                counts["examined"] += 1
                nid = graph_node_id(ctx.tenant_id, node_type, entity_id)
                node = DeliveryGraphNode(
                    tenant_id=ctx.tenant_id,
                    graph_node_id=nid,
                    node_type=node_type,
                    entity_id=entity_id,
                    canonical_key=f"{node_type.value}:{entity_id}",
                    display_label=_label(label, entity_id),
                    source_entity_version=None,
                    first_observed_at=getattr(row, "created_at", None) or now,
                    last_observed_at=getattr(row, "updated_at", None) or now,
                    archived_at=archived_at,
                    projection_version=GRAPH_PROJECTION_VERSION,
                )
                _, created = self._uow.graph_nodes.upsert_node(ctx, node)
                if created:
                    counts["created"] += 1
                else:
                    counts["updated"] += 1
                index[(node_type, entity_id)] = nid
        return index, counts

    def _rows(
        self,
        model,
        ctx: TenantContext,
        since: datetime | None,
        *,
        hwm_samples: list[datetime] | None = None,
    ):
        query = select(model).where(model.tenant_id == ctx.tenant_id)
        if since is not None and hasattr(model, "updated_at"):
            # Inclusive equal-timestamp: use >= so equal timestamps are not skipped.
            query = query.where(model.updated_at >= since)
        # Deterministic ordering by primary key attribute name heuristics.
        pk = list(model.__table__.primary_key.columns)[0]
        query = query.order_by(pk.asc())
        rows = self._uow.session.scalars(query).all()
        if hwm_samples is not None and hasattr(model, "updated_at"):
            for row in rows:
                ts = getattr(row, "updated_at", None)
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                hwm_samples.append(ts)
        return rows

    # ------------------------------------------------------------------ edges
    def _project_edges(
        self,
        ctx: TenantContext,
        node_index: dict[tuple[GraphNodeType, str], str],
        *,
        since: datetime | None,
        subject_ids: list[str] | None,
        hwm_samples: list[datetime] | None = None,
    ) -> tuple[dict[str, int], set[str]]:
        counts = {"examined": 0, "created": 0, "updated": 0, "closed": 0, "unchanged": 0}
        desired: set[str] = set()
        now = _utcnow()
        subject_set = set(subject_ids) if subject_ids else None
        entity_by_node = {nid: eid for (_nt, eid), nid in node_index.items()}

        def resolve(node_type: GraphNodeType, entity_id: str | None) -> str | None:
            if not entity_id:
                return None
            return node_index.get((node_type, entity_id))

        def emit(edge: DeliveryGraphEdge) -> None:
            if subject_set is not None:
                s_ent = entity_by_node.get(edge.source_node_id)
                t_ent = entity_by_node.get(edge.target_node_id)
                if s_ent not in subject_set and t_ent not in subject_set:
                    return
            counts["examined"] += 1
            desired.add(edge.graph_edge_id)
            _, action = self._uow.graph_edges.upsert_edge(ctx, edge)
            if action == "created":
                counts["created"] += 1
            elif action == "updated":
                counts["updated"] += 1
            else:
                counts["unchanged"] += 1
            logger.debug(
                "graph.edge.projected tenant_id=%s edge_id=%s type=%s action=%s",
                ctx.tenant_id,
                edge.graph_edge_id,
                edge.edge_type.value,
                action,
            )

        def make_edge(
            *,
            source: str,
            target: str,
            edge_type: GraphEdgeType,
            origin: GraphEdgeOrigin,
            natural_key: str,
            valid_from: datetime,
            valid_to: datetime | None = None,
            criticality: str = "medium",
            ownership_id: str | None = None,
            dependency_id: str | None = None,
            evidence_id: str | None = None,
            derivation_rule: str | None = None,
            attributes: dict | None = None,
            observed_at: datetime | None = None,
        ) -> DeliveryGraphEdge | None:
            if source == target:
                return None
            obs = observed_at or valid_from or now
            # SQLite may return naive datetimes; normalize to UTC-aware.
            if obs is not None and obs.tzinfo is None:
                obs = obs.replace(tzinfo=timezone.utc)
            if valid_from is not None and valid_from.tzinfo is None:
                valid_from = valid_from.replace(tzinfo=timezone.utc)
            if valid_to is not None and valid_to.tzinfo is None:
                valid_to = valid_to.replace(tzinfo=timezone.utc)
            conf, _warnings = edge_confidence(origin=origin, observed_at=obs, now=now)
            attrs = attributes or {}
            payload = {
                "source": source,
                "target": target,
                "edge_type": edge_type.value,
                "origin": origin.value,
                "natural_key": natural_key,
                "attributes": attrs,
                "ownership_id": ownership_id,
                "dependency_id": dependency_id,
                "evidence_id": evidence_id,
                "derivation_rule": derivation_rule,
            }
            eid = graph_edge_id(ctx.tenant_id, source, target, edge_type, natural_key)
            return DeliveryGraphEdge(
                tenant_id=ctx.tenant_id,
                graph_edge_id=eid,
                source_node_id=source,
                target_node_id=target,
                edge_type=edge_type,
                edge_origin=origin,
                confidence=conf,
                criticality=criticality,
                valid_from=valid_from,
                valid_to=valid_to,
                first_observed_at=obs,
                last_observed_at=obs,
                supporting_evidence_signal_id=evidence_id,
                supporting_ownership_id=ownership_id,
                supporting_dependency_id=dependency_id,
                derivation_rule=derivation_rule,
                derivation_version=GRAPH_DERIVATION_VERSION if derivation_rule else None,
                attributes=attrs,
                payload_hash=snapshot_hash(payload),
                projection_version=GRAPH_PROJECTION_VERSION,
            )

        # --- Organization structure (catalog) ---
        for bu in self._rows(ent_orm.BusinessUnit, ctx, since, hwm_samples=hwm_samples):
            s = resolve(GraphNodeType.BUSINESS_UNIT, bu.business_unit_id)
            t = resolve(GraphNodeType.ORGANIZATION, bu.organization_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.MEMBER_OF,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"bu-member:{bu.business_unit_id}",
                    valid_from=bu.valid_from,
                    valid_to=bu.valid_to,
                    attributes={"source_entity": "business_unit"},
                )
                if edge:
                    emit(edge)

        for dept in self._rows(ent_orm.Department, ctx, since, hwm_samples=hwm_samples):
            s = resolve(GraphNodeType.DEPARTMENT, dept.department_id)
            t = resolve(GraphNodeType.BUSINESS_UNIT, dept.business_unit_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.MEMBER_OF,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"dept-member:{dept.department_id}",
                    valid_from=getattr(dept, "created_at", None) or now,
                    attributes={"source_entity": "department"},
                )
                if edge:
                    emit(edge)

        for team in self._rows(ent_orm.Team, ctx, since, hwm_samples=hwm_samples):
            s = resolve(GraphNodeType.TEAM, team.team_id)
            t = resolve(GraphNodeType.DEPARTMENT, team.department_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.MEMBER_OF,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"team-member:{team.team_id}",
                    valid_from=getattr(team, "created_at", None) or now,
                    attributes={"source_entity": "team"},
                )
                if edge:
                    emit(edge)

        for eng in self._rows(ent_orm.EngineerProfile, ctx, since, hwm_samples=hwm_samples):
            s = resolve(GraphNodeType.ENGINEER, eng.engineer_profile_id)
            t = resolve(GraphNodeType.TEAM, eng.current_team_id) if eng.current_team_id else None
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.MEMBER_OF,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"eng-member:{eng.engineer_profile_id}",
                    valid_from=eng.valid_from,
                    valid_to=eng.valid_to,
                    attributes={"source_entity": "engineer_profile"},
                )
                if edge:
                    emit(edge)

        for proj in self._rows(ent_orm.EnterpriseProject, ctx, since, hwm_samples=hwm_samples):
            s = resolve(GraphNodeType.PROJECT, proj.enterprise_project_id)
            t = resolve(GraphNodeType.INITIATIVE, proj.initiative_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.CONTRIBUTES_TO,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"proj-init:{proj.enterprise_project_id}",
                    valid_from=getattr(proj, "created_at", None) or now,
                    criticality=proj.criticality or "medium",
                )
                if edge:
                    emit(edge)
            if proj.owning_team_id:
                team_node = resolve(GraphNodeType.TEAM, proj.owning_team_id)
                if s and team_node:
                    edge = make_edge(
                        source=team_node,
                        target=s,
                        edge_type=GraphEdgeType.OWNS,
                        origin=GraphEdgeOrigin.CATALOG,
                        natural_key=f"team-owns-proj:{proj.owning_team_id}:{proj.enterprise_project_id}",
                        valid_from=getattr(proj, "created_at", None) or now,
                        criticality=proj.criticality or "medium",
                    )
                    if edge:
                        emit(edge)

        for repo in self._rows(ent_orm.Repository, ctx, since, hwm_samples=hwm_samples):
            if repo.owning_team_id:
                s = resolve(GraphNodeType.TEAM, repo.owning_team_id)
                t = resolve(GraphNodeType.REPOSITORY, repo.repository_id)
                if s and t:
                    edge = make_edge(
                        source=s,
                        target=t,
                        edge_type=GraphEdgeType.OWNS,
                        origin=GraphEdgeOrigin.CATALOG,
                        natural_key=f"team-owns-repo:{repo.owning_team_id}:{repo.repository_id}",
                        valid_from=getattr(repo, "created_at", None) or now,
                    )
                    if edge:
                        emit(edge)

        # Capability skill links as requires
        for link in self._rows(ent_orm.CapabilitySkill, ctx, since, hwm_samples=hwm_samples):
            s = resolve(GraphNodeType.CAPABILITY, link.capability_id)
            t = resolve(GraphNodeType.SKILL, link.skill_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.REQUIRES,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"cap-skill:{link.capability_skill_id}",
                    valid_from=getattr(link, "created_at", None) or now,
                )
                if edge:
                    emit(edge)

        # Engineer capability evidence -> contributes_to / owns capability
        for ev in self._rows(
            ent_orm.EngineerCapabilityEvidence, ctx, since, hwm_samples=hwm_samples
        ):
            s = resolve(GraphNodeType.ENGINEER, ev.engineer_profile_id)
            t = resolve(GraphNodeType.CAPABILITY, ev.capability_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.CONTRIBUTES_TO,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"eng-cap:{ev.evidence_id}",
                    valid_from=ev.valid_from,
                    valid_to=ev.valid_to,
                    attributes={"proficiency_band": "declared"},
                )
                if edge:
                    emit(edge)

        # Ownership records
        for own in self._rows(ent_orm.Ownership, ctx, since, hwm_samples=hwm_samples):
            owner_type = _ENTITY_TO_NODE.get(own.owner_type)
            resource_type = _ENTITY_TO_NODE.get(own.resource_type)
            if not owner_type or not resource_type:
                continue
            s = resolve(owner_type, own.owner_id)
            t = resolve(resource_type, own.resource_id)
            edge_type = _OWNERSHIP_EDGE.get(own.ownership_type, GraphEdgeType.SUPPORTS)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=edge_type,
                    origin=GraphEdgeOrigin.MANUAL,
                    natural_key=f"own:{own.ownership_id}",
                    valid_from=own.valid_from,
                    valid_to=own.valid_to,
                    ownership_id=own.ownership_id,
                    attributes={
                        "ownership_type": own.ownership_type,
                        "allocation": own.allocation,
                    },
                )
                if edge:
                    emit(edge)

        # Dependency records
        for dep in self._rows(ent_orm.Dependency, ctx, since, hwm_samples=hwm_samples):
            if dep.status != "active":
                continue
            s_type = _ENTITY_TO_NODE.get(dep.source_type)
            t_type = _ENTITY_TO_NODE.get(dep.target_type)
            if not s_type or not t_type:
                continue
            s = resolve(s_type, dep.source_id)
            t = resolve(t_type, dep.target_id)
            edge_type = _DEPENDENCY_EDGE.get(dep.dependency_type, GraphEdgeType.DEPENDS_ON)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=edge_type,
                    origin=GraphEdgeOrigin.MANUAL,
                    natural_key=f"dep:{dep.dependency_id}",
                    valid_from=dep.valid_from,
                    valid_to=dep.valid_to,
                    criticality=dep.criticality,
                    dependency_id=dep.dependency_id,
                    attributes={"dependency_type": dep.dependency_type},
                )
                if edge:
                    emit(edge)

        # Work items contribute to projects
        for wi in self._rows(ent_orm.WorkItem, ctx, since, hwm_samples=hwm_samples):
            if not wi.enterprise_project_id:
                continue
            s = resolve(GraphNodeType.WORK_ITEM, wi.work_item_id)
            t = resolve(GraphNodeType.PROJECT, wi.enterprise_project_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.CONTRIBUTES_TO,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"wi-proj:{wi.work_item_id}",
                    valid_from=wi.source_created_at or getattr(wi, "created_at", None) or now,
                )
                if edge:
                    emit(edge)

        # Pull requests contribute to repositories
        for pr in self._rows(ent_orm.PullRequest, ctx, since, hwm_samples=hwm_samples):
            if not pr.repository_id:
                continue
            s = resolve(GraphNodeType.PULL_REQUEST, pr.pull_request_id)
            t = resolve(GraphNodeType.REPOSITORY, pr.repository_id)
            if s and t:
                origin = (
                    GraphEdgeOrigin.CONNECTOR
                    if pr.source_precedence == "connector"
                    else GraphEdgeOrigin.CATALOG
                )
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.CONTRIBUTES_TO,
                    origin=origin,
                    natural_key=f"pr-repo:{pr.pull_request_id}",
                    valid_from=pr.created_at_source or getattr(pr, "created_at", None) or now,
                    evidence_id=pr.last_evidence_signal_id,
                    attributes={"pr_state": pr.state},
                )
                if edge:
                    emit(edge)

        # Deployments deployed_by repository
        for dep in self._rows(ent_orm.Deployment, ctx, since, hwm_samples=hwm_samples):
            if not dep.repository_id:
                continue
            s = resolve(GraphNodeType.DEPLOYMENT, dep.deployment_id)
            t = resolve(GraphNodeType.REPOSITORY, dep.repository_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.DEPLOYED_BY,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"deploy-repo:{dep.deployment_id}",
                    valid_from=dep.started_at,
                )
                if edge:
                    emit(edge)

        # Incidents respond_to repository
        for inc in self._rows(ent_orm.Incident, ctx, since, hwm_samples=hwm_samples):
            if not inc.repository_id:
                continue
            s = resolve(GraphNodeType.INCIDENT, inc.incident_id)
            t = resolve(GraphNodeType.REPOSITORY, inc.repository_id)
            if s and t:
                edge = make_edge(
                    source=s,
                    target=t,
                    edge_type=GraphEdgeType.RESPONDS_TO,
                    origin=GraphEdgeOrigin.CATALOG,
                    natural_key=f"inc-repo:{inc.incident_id}",
                    valid_from=inc.started_at,
                    criticality="high" if inc.severity in {"sev1", "sev2"} else "medium",
                )
                if edge:
                    emit(edge)

        # Derived: team supports initiative via owning projects.
        # Natural key MUST include the project id. Collapsing to (team, initiative)
        # alone makes via_project_id flip the payload hash across projects that
        # share a team+initiative; temporal closure then uses each project's
        # created_at as closed_at and can insert valid_to <= valid_from.
        for proj in self._rows(ent_orm.EnterpriseProject, ctx, since, hwm_samples=hwm_samples):
            if not proj.owning_team_id:
                continue
            team_node = resolve(GraphNodeType.TEAM, proj.owning_team_id)
            init_node = resolve(GraphNodeType.INITIATIVE, proj.initiative_id)
            if team_node and init_node:
                # Prefer planned_start (business interval) over wall-clock created_at.
                proj_from = (
                    getattr(proj, "planned_start", None) or getattr(proj, "created_at", None) or now
                )
                edge = make_edge(
                    source=team_node,
                    target=init_node,
                    edge_type=GraphEdgeType.SUPPORTS,
                    origin=GraphEdgeOrigin.DERIVED,
                    natural_key=(
                        "derived-team-supports-init:"
                        f"{proj.owning_team_id}:{proj.initiative_id}:{proj.enterprise_project_id}"
                    ),
                    valid_from=proj_from,
                    derivation_rule="team_owns_project_contributes_to_initiative",
                    attributes={"via_project_id": proj.enterprise_project_id},
                    criticality=proj.criticality or "medium",
                )
                if edge:
                    emit(edge)

        # Derived: repository supports project when ownership + project dependency
        # via shared team ownership of both
        repo_by_team: dict[str, list[str]] = {}
        for repo in self._rows(ent_orm.Repository, ctx, since, hwm_samples=hwm_samples):
            if repo.owning_team_id:
                repo_by_team.setdefault(repo.owning_team_id, []).append(repo.repository_id)
        for proj in self._rows(ent_orm.EnterpriseProject, ctx, since, hwm_samples=hwm_samples):
            if not proj.owning_team_id:
                continue
            for repo_id in repo_by_team.get(proj.owning_team_id, []):
                s = resolve(GraphNodeType.REPOSITORY, repo_id)
                t = resolve(GraphNodeType.PROJECT, proj.enterprise_project_id)
                if s and t:
                    edge = make_edge(
                        source=s,
                        target=t,
                        edge_type=GraphEdgeType.SUPPORTS,
                        origin=GraphEdgeOrigin.DERIVED,
                        natural_key=f"derived-repo-supports-proj:{repo_id}:{proj.enterprise_project_id}",
                        valid_from=(
                            getattr(proj, "planned_start", None)
                            or getattr(proj, "created_at", None)
                            or now
                        ),
                        derivation_rule="shared_team_ownership_repo_project",
                        attributes={"team_id": proj.owning_team_id},
                    )
                    if edge:
                        emit(edge)

        return counts, desired

    def _close_obsolete_edges(
        self, ctx: TenantContext, desired: set[str], closed_at: datetime
    ) -> int:
        closed = 0
        for edge_id in self._uow.graph_edges.list_open_edge_ids(ctx):
            if edge_id not in desired:
                self._uow.graph_edges.close_edge(ctx, edge_id, closed_at)
                closed += 1
                logger.info(
                    "graph.edge.closed tenant_id=%s edge_id=%s",
                    ctx.tenant_id,
                    edge_id,
                )
        return closed

    def _archive_orphan_nodes(
        self, ctx: TenantContext, live_node_ids: set[str], archived_at: datetime
    ) -> int:
        archived = 0
        for node_id in self._uow.graph_nodes.list_all_node_ids(ctx, include_archived=False):
            if node_id not in live_node_ids:
                self._uow.graph_nodes.archive_node(ctx, node_id, archived_at)
                archived += 1
        return archived
