"""Audit regression tests for Prompt 3 delivery-graph fixes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.graph_enums import GraphEdgeOrigin, GraphEdgeType, GraphNodeType
from app.domain.graph_models import DeliveryGraphEdge, DeliveryGraphNode
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseConflictError
from app.services.graph.projection_service import GraphProjectionService, graph_node_id
from app.services.persistence.snapshot_service import snapshot_hash

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)


def _seed_two_nodes(uow: UnitOfWork, ctx: TenantContext) -> tuple[str, str]:
    a = DeliveryGraphNode(
        tenant_id=ctx.tenant_id,
        graph_node_id=graph_node_id(ctx.tenant_id, GraphNodeType.TEAM, "audit-a"),
        node_type=GraphNodeType.TEAM,
        entity_id="audit-a",
        canonical_key="team:audit-a",
        display_label="Audit A",
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    b = DeliveryGraphNode(
        tenant_id=ctx.tenant_id,
        graph_node_id=graph_node_id(ctx.tenant_id, GraphNodeType.TEAM, "audit-b"),
        node_type=GraphNodeType.TEAM,
        entity_id="audit-b",
        canonical_key="team:audit-b",
        display_label="Audit B",
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    uow.graph_nodes.upsert_node(ctx, a)
    uow.graph_nodes.upsert_node(ctx, b)
    return a.graph_node_id, b.graph_node_id


def test_edge_payload_change_retains_historical_snapshot(migrated_db, tenant_a):
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        src, tgt = _seed_two_nodes(uow, tenant_a)
        edge = DeliveryGraphEdge(
            tenant_id=tenant_a.tenant_id,
            graph_edge_id="gedge_audit_hist_1",
            source_node_id=src,
            target_node_id=tgt,
            edge_type=GraphEdgeType.DEPENDS_ON,
            edge_origin=GraphEdgeOrigin.MANUAL,
            valid_from=NOW,
            first_observed_at=NOW,
            last_observed_at=NOW,
            supporting_dependency_id="dep_audit_1",
            attributes={"rev": 1},
            payload_hash=snapshot_hash({"rev": 1}),
        )
        uow.graph_edges.upsert_edge(tenant_a, edge)
        uow.commit()

        later = NOW + timedelta(hours=1)
        updated = edge.model_copy(
            update={
                "valid_from": later,
                "first_observed_at": later,
                "last_observed_at": later,
                "attributes": {"rev": 2},
                "payload_hash": snapshot_hash({"rev": 2}),
            }
        )
        uow.graph_edges.upsert_edge(tenant_a, updated)
        uow.commit()

        open_edge = uow.graph_edges.get_edge(tenant_a, "gedge_audit_hist_1")
        assert open_edge is not None
        assert open_edge.attributes["rev"] == 2
        assert open_edge.valid_to is None

        mid = NOW + timedelta(minutes=30)
        historical = uow.graph_edges.list_edges(tenant_a, active_at=mid, limit=100)
        assert historical.total == 1
        assert historical.items[0].attributes["rev"] == 1
        assert historical.items[0].graph_edge_id != "gedge_audit_hist_1"
        assert historical.items[0].valid_to is not None


def test_incremental_includes_equal_timestamp_sources(seeded_db, novabank_tenant):
    from sqlalchemy import select

    from app.db.models import enterprise as ent_orm

    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        run1 = GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        assert run1.source_high_watermark is not None

        # Force HWM to a known point, then bump ownership rows to the same ts.
        hwm = run1.source_high_watermark
        equal_ts = hwm + timedelta(minutes=1)
        ownerships = session.scalars(
            select(ent_orm.Ownership).where(
                ent_orm.Ownership.tenant_id == novabank_tenant.tenant_id
            )
        ).all()
        for row in ownerships:
            row.updated_at = equal_ts
        session.commit()

        # Simulate prior HWM exactly at equal_ts (no overlap subtraction via since=).
        run2 = GraphProjectionService(uow).incremental_refresh(novabank_tenant, since=equal_ts)
        uow.commit()
        assert run2.state.value == "succeeded"
        # Inclusive >= must examine ownership-derived edges (not skip equals).
        assert run2.edges_examined > 0


def test_subject_refresh_scopes_edge_emission(seeded_db, novabank_tenant):
    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        page = uow.graph_nodes.list_nodes(
            novabank_tenant, node_type=GraphNodeType.ENGINEER, limit=1
        )
        subject = page.items[0].entity_id
        run = GraphProjectionService(uow).subject_refresh(novabank_tenant, [subject])
        uow.commit()
        assert run.state.value == "succeeded"
        assert subject in run.subject_ids
        # Subject refresh should examine fewer edges than a full tenant edge set.
        full = GraphProjectionService(uow).incremental_refresh(
            novabank_tenant, since=datetime(2000, 1, 1, tzinfo=timezone.utc)
        )
        uow.commit()
        assert run.edges_examined < full.edges_examined


def test_rebuild_failure_preserves_prior_graph(seeded_db, novabank_tenant, monkeypatch):
    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        before_nodes = uow.graph_nodes.list_all_node_ids(novabank_tenant)
        before_edges = uow.graph_edges.list_open_edge_ids(novabank_tenant)
        assert before_nodes and before_edges

        def boom(*_a, **_k):
            raise RuntimeError("audit_injected_failure")

        monkeypatch.setattr(GraphProjectionService, "_project_edges", boom)
        with pytest.raises(RuntimeError, match="audit_injected_failure"):
            GraphProjectionService(uow).full_rebuild(novabank_tenant)

        # New session: prior graph intact; failed run recorded.
        with Session(engine) as session2:
            uow2 = UnitOfWork(session2)
            assert uow2.graph_nodes.list_all_node_ids(novabank_tenant) == before_nodes
            assert uow2.graph_edges.list_open_edge_ids(novabank_tenant) == before_edges
            runs = uow2.graph_projection_runs.list_runs(novabank_tenant, limit=5)
            assert any(r.state.value == "failed" for r in runs.items)
            assert any(r.state.value == "succeeded" for r in runs.items)


def test_durable_rebuild_lock_visible_across_sessions(seeded_db, novabank_tenant, monkeypatch):
    from sqlalchemy import select

    from app.db.models import graph as graph_orm

    engine = get_engine(seeded_db)

    def hang_after_lock(self, ctx, *, since=None, subject_ids=None, hwm_samples=None):
        raise RuntimeError("stop_after_nodes")

    with Session(engine) as session:
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()

    monkeypatch.setattr(GraphProjectionService, "_project_nodes", hang_after_lock)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        with pytest.raises(RuntimeError, match="stop_after_nodes"):
            GraphProjectionService(uow).full_rebuild(novabank_tenant)

    monkeypatch.undo()

    with Session(engine) as session2:
        uow2 = UnitOfWork(session2)
        # Failure recorder marks FAILED so a fresh rebuild is allowed.
        run = GraphProjectionService(uow2).full_rebuild(novabank_tenant)
        uow2.commit()
        assert run.state.value == "succeeded"

    # Artificial stuck RUNNING row must conflict across sessions.
    with Session(engine) as session:
        latest = session.scalars(
            select(graph_orm.GraphProjectionRun)
            .where(
                graph_orm.GraphProjectionRun.tenant_id == novabank_tenant.tenant_id,
                graph_orm.GraphProjectionRun.mode == "full_rebuild",
            )
            .order_by(graph_orm.GraphProjectionRun.started_at.desc())
        ).first()
        assert latest is not None
        latest.state = "running"
        latest.started_at = datetime.now(timezone.utc)
        session.commit()

    with Session(engine) as session:
        uow = UnitOfWork(session)
        with pytest.raises(EnterpriseConflictError):
            GraphProjectionService(uow).full_rebuild(novabank_tenant)


def test_temporal_closure_rejects_inverted_hist_interval(migrated_db, tenant_a):
    """Payload flip with earlier successor valid_from must not violate valid_interval."""
    from datetime import datetime, timezone

    from sqlalchemy.orm import Session

    from app.db.session import get_engine
    from app.db.unit_of_work import UnitOfWork
    from app.domain.graph_enums import GraphEdgeOrigin, GraphEdgeType, GraphNodeType
    from app.domain.graph_models import DeliveryGraphEdge, DeliveryGraphNode
    from app.services.graph.projection_service import graph_node_id
    from app.services.persistence.snapshot_service import snapshot_hash

    earlier = datetime(2026, 7, 28, 12, 0, 0, 100, tzinfo=timezone.utc)
    later = datetime(2026, 7, 28, 12, 0, 0, 500, tzinfo=timezone.utc)
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        a = DeliveryGraphNode(
            tenant_id=tenant_a.tenant_id,
            graph_node_id=graph_node_id(tenant_a.tenant_id, GraphNodeType.TEAM, "inv-a"),
            node_type=GraphNodeType.TEAM,
            entity_id="inv-a",
            canonical_key="team:inv-a",
            display_label="Inv A",
            first_observed_at=later,
            last_observed_at=later,
        )
        b = DeliveryGraphNode(
            tenant_id=tenant_a.tenant_id,
            graph_node_id=graph_node_id(tenant_a.tenant_id, GraphNodeType.INITIATIVE, "inv-b"),
            node_type=GraphNodeType.INITIATIVE,
            entity_id="inv-b",
            canonical_key="init:inv-b",
            display_label="Inv B",
            first_observed_at=later,
            last_observed_at=later,
        )
        uow.graph_nodes.upsert_node(tenant_a, a)
        uow.graph_nodes.upsert_node(tenant_a, b)
        first = DeliveryGraphEdge(
            tenant_id=tenant_a.tenant_id,
            graph_edge_id="gedge_inv_hist_1",
            source_node_id=a.graph_node_id,
            target_node_id=b.graph_node_id,
            edge_type=GraphEdgeType.SUPPORTS,
            edge_origin=GraphEdgeOrigin.DERIVED,
            valid_from=later,
            first_observed_at=later,
            last_observed_at=later,
            derivation_rule="team_owns_project_contributes_to_initiative",
            attributes={"via_project_id": "proj_later"},
            payload_hash=snapshot_hash({"via": "later"}),
        )
        uow.graph_edges.upsert_edge(tenant_a, first)
        uow.commit()
        # Successor starts earlier than existing open interval — must not insert
        # hist row with valid_to < valid_from.
        second = first.model_copy(
            update={
                "valid_from": earlier,
                "first_observed_at": earlier,
                "last_observed_at": earlier,
                "attributes": {"via_project_id": "proj_earlier"},
                "payload_hash": snapshot_hash({"via": "earlier"}),
            }
        )
        uow.graph_edges.upsert_edge(tenant_a, second)
        uow.commit()
        open_edge = uow.graph_edges.get_edge(tenant_a, "gedge_inv_hist_1")
        assert open_edge is not None
        assert open_edge.attributes["via_project_id"] == "proj_earlier"
        assert open_edge.valid_to is None
