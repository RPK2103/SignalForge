"""Projection, analysis, tenant isolation, and NovaBank scenario tests."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.enterprise_seed import seed_enterprise
from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.graph_enums import GraphEdgeOrigin, GraphFindingType, GraphNodeType
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.projection_service import GraphProjectionService, graph_node_id
from app.services.graph.query_service import DeliveryGraphQueryService


def test_full_rebuild_idempotent(seeded_db, novabank_tenant):
    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        run1 = GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        assert run1.state.value == "succeeded"
        assert run1.nodes_created > 0
        assert run1.edges_created > 0
        created_nodes = run1.nodes_created

        run2 = GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        assert run2.state.value == "succeeded"
        assert run2.nodes_created == 0
        assert run2.edges_created == 0
        assert run2.nodes_updated >= created_nodes or run2.nodes_examined >= created_nodes

        summary = DeliveryGraphQueryService(uow).summary(novabank_tenant)
        assert summary.node_count >= created_nodes
        assert summary.edge_count >= 1
        # Second rebuild must not inflate counts via duplicates.
        node_ids = uow.graph_nodes.list_all_node_ids(novabank_tenant)
        assert len(node_ids) == len(set(node_ids))
        open_edges = uow.graph_edges.list_open_edge_ids(novabank_tenant)
        assert len(open_edges) == len(set(open_edges))


def test_subject_refresh(seeded_db, novabank_tenant):
    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        # Pick a known seeded engineer entity id via node list.
        page = uow.graph_nodes.list_nodes(
            novabank_tenant, node_type=GraphNodeType.ENGINEER, limit=1
        )
        assert page.items
        subject = page.items[0].entity_id
        run = GraphProjectionService(uow).subject_refresh(novabank_tenant, [subject])
        uow.commit()
        assert run.state.value == "succeeded"
        assert subject in run.subject_ids


def test_tenant_isolation_nodes_edges_findings(seeded_db, novabank_tenant, tenant_b):
    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        GraphAnalysisService(uow).analyze(novabank_tenant)
        uow.commit()

        nb_nodes = uow.graph_nodes.list_nodes(novabank_tenant, limit=5)
        assert nb_nodes.total > 0
        foreign = uow.graph_nodes.get_node(tenant_b, nb_nodes.items[0].graph_node_id)
        assert foreign is None

        edges = uow.graph_edges.list_edges(novabank_tenant, limit=5)
        if edges.items:
            assert uow.graph_edges.get_edge(tenant_b, edges.items[0].graph_edge_id) is None

        findings = uow.graph_findings.list_findings(novabank_tenant, limit=5)
        if findings.items:
            assert (
                uow.graph_findings.get_finding(tenant_b, findings.items[0].graph_finding_id) is None
            )


def test_cross_tenant_edge_rejected(seeded_db, novabank_tenant, tenant_b):
    from datetime import datetime, timezone

    import pytest

    from app.domain.graph_enums import GraphEdgeOrigin, GraphEdgeType
    from app.domain.graph_models import DeliveryGraphEdge, DeliveryGraphNode
    from app.services.enterprise.exceptions import CrossTenantAccessError
    from app.services.persistence.snapshot_service import snapshot_hash

    now = datetime.now(timezone.utc)
    engine = get_engine(seeded_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        # Create a node in tenant B only.
        node_b = DeliveryGraphNode(
            tenant_id=tenant_b.tenant_id,
            graph_node_id=graph_node_id(tenant_b.tenant_id, GraphNodeType.TEAM, "tb1"),
            node_type=GraphNodeType.TEAM,
            entity_id="tb1",
            canonical_key="team:tb1",
            display_label="Tenant B Team",
            first_observed_at=now,
            last_observed_at=now,
        )
        uow.graph_nodes.upsert_node(tenant_b, node_b)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        uow.commit()
        nb = uow.graph_nodes.list_nodes(novabank_tenant, limit=1).items[0]
        edge = DeliveryGraphEdge(
            tenant_id=novabank_tenant.tenant_id,
            graph_edge_id="gedge_cross",
            source_node_id=nb.graph_node_id,
            target_node_id=node_b.graph_node_id,
            edge_type=GraphEdgeType.DEPENDS_ON,
            edge_origin=GraphEdgeOrigin.MANUAL,
            valid_from=now,
            first_observed_at=now,
            last_observed_at=now,
            supporting_dependency_id="dep_x",
            payload_hash=snapshot_hash({"cross": True}),
        )
        with pytest.raises(CrossTenantAccessError):
            uow.graph_edges.upsert_edge(novabank_tenant, edge)


def test_analysis_idempotent_and_findings(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        before = uow.graph_findings.list_findings(novabank_tenant, limit=100)
        run2 = GraphAnalysisService(uow).analyze(novabank_tenant)
        uow.commit()
        assert run2.findings_created == 0
        after = uow.graph_findings.list_findings(novabank_tenant, limit=100)
        assert after.total == before.total
        assert after.total > 0
        types = {f.finding_type for f in after.items}
        # At least cycle finding from NovaBank demo cycle.
        assert GraphFindingType.DEPENDENCY_CYCLE in types or any(
            f.finding_type == GraphFindingType.DEPENDENCY_CYCLE
            for f in uow.graph_findings.list_findings(
                novabank_tenant, finding_type=GraphFindingType.DEPENDENCY_CYCLE, limit=10
            ).items
        )


def test_novabank_scenarios(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        query = DeliveryGraphQueryService(uow)
        summary = query.summary(novabank_tenant)
        assert summary.node_count > 50
        assert summary.edge_count > 50
        assert summary.edges_by_origin.get(GraphEdgeOrigin.DERIVED.value, 0) >= 1
        assert summary.edges_by_origin.get(GraphEdgeOrigin.CATALOG.value, 0) >= 1

        cycles = query.dependency_cycles(novabank_tenant)
        assert len(cycles) >= 1

        # Fraud scoring repo concentration
        repos = uow.graph_nodes.list_nodes(
            novabank_tenant, node_type=GraphNodeType.REPOSITORY, limit=100
        )
        fraud = next(r for r in repos.items if "fraud-scoring" in r.display_label)
        conc = query.ownership_concentration(novabank_tenant, fraud.graph_node_id)
        assert conc.single_owner or conc.low_redundancy

        findings = uow.graph_findings.list_findings(novabank_tenant, limit=100)
        finding_types = {f.finding_type for f in findings.items}
        assert GraphFindingType.REPOSITORY_OWNERSHIP_CONCENTRATION in finding_types
        assert GraphFindingType.DEPENDENCY_CYCLE in finding_types


def test_historical_active_at(projected_novabank, novabank_tenant):
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        # Edges valid_from is 2026-01-06 in seed — past should see fewer/none active.
        page = uow.graph_edges.list_edges(novabank_tenant, active_at=past, limit=10)
        assert page.total == 0


def test_seed_second_run_zero_duplicates(migrated_db):
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        first = seed_enterprise(session)
        session.commit()
        second = seed_enterprise(session)
        session.commit()
    assert first["total_created"] > 0
    assert second["total_created"] == 0


def test_concurrent_tenants_unaffected(seeded_db, novabank_tenant, tenant_a):
    from app.db.models import enterprise as orm
    from app.domain.enterprise_identifiers import build_entity_id

    engine = get_engine(seeded_db)
    with Session(engine) as session:
        # Minimal tenant-a org so projection has something.
        org_id = build_entity_id("org", tenant_a.tenant_id, "a")
        session.add(
            orm.Organization(
                organization_id=org_id,
                tenant_id=tenant_a.tenant_id,
                name="Tenant A",
                slug="tenant-a",
                organization_type="startup",
                timezone_name="UTC",
            )
        )
        session.commit()
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(novabank_tenant)
        GraphProjectionService(uow).full_rebuild(tenant_a)
        uow.commit()
        nb = DeliveryGraphQueryService(uow).summary(novabank_tenant)
        ta = DeliveryGraphQueryService(uow).summary(tenant_a)
        assert nb.node_count > ta.node_count
        assert ta.node_count >= 1
