"""Execution, immutability, watches, comparison, and tenancy tests."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import enterprise as ent_orm
from app.db.models import graph as graph_orm
from app.db.models import prediction as pred_orm
from app.db.unit_of_work import UnitOfWork
from app.domain.scenario_enums import ComparisonDimension, ScenarioTriggerAction
from app.domain.tenant_context import TenantContext
from app.services.scenarios.orchestration import ScenarioOrchestrationService
from tests.scenarios.conftest import AS_OF


def test_seed_idempotent(seeded_novabank, db_session: Session, novabank_tenant: TenantContext):
    from app.db.scenario_seed import seed_novabank_scenarios

    first = seeded_novabank["scenarios"]
    second = seed_novabank_scenarios(db_session)
    db_session.commit()
    assert first["scenario_count"] == 8
    assert second["definitions_created"] == 0
    assert second["versions_created"] == 0


def test_execute_all_kinds_and_idempotent_reuse(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_ids = seeded_novabank["scenarios"]["version_ids"]
    hashes = []
    for version_id in version_ids:
        bundle = orch.run(novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF)
        assert bundle.result is not None
        assert bundle.result.baseline_estimate_kind.value == "uncalibrated_score"
        assert bundle.result.baseline_probability is None
        assert bundle.result.simulated_probability is None
        assert "uncalibrated_score_not_probability" in bundle.result.applicability_warnings
        assert bundle.feature_overlay is not None
        assert bundle.feature_overlay.training_eligible is False
        hashes.append(bundle.result.result_hash)
    uow.commit()

    # Identical re-run reuses.
    uow2 = UnitOfWork(db_session)
    orch2 = ScenarioOrchestrationService(uow2)
    again = orch2.run(novabank_tenant, scenario_version_id=version_ids[0], as_of_at=AS_OF)
    assert again.reused_existing is True
    assert again.result is not None
    assert again.result.result_hash == hashes[0]


def test_source_immutability_after_execution(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    uow = UnitOfWork(db_session)
    before_owners = db_session.scalars(select(ent_orm.Ownership)).all()
    before_owner_ids = sorted(o.ownership_id for o in before_owners)
    before_nodes = db_session.scalars(select(graph_orm.DeliveryGraphNode)).all()
    before_node_ids = sorted(n.graph_node_id for n in before_nodes)
    before_edges = db_session.scalars(select(graph_orm.DeliveryGraphEdge)).all()
    before_edge_ids = sorted(e.graph_edge_id for e in before_edges)
    before_snaps = db_session.scalars(select(pred_orm.PredictionFeatureSnapshot)).all()
    before_snap_ids = sorted(s.prediction_feature_snapshot_id for s in before_snaps)
    before_preds = db_session.scalars(select(pred_orm.DeliveryPrediction)).all()
    before_pred_ids = sorted(p.delivery_prediction_id for p in before_preds)

    orch = ScenarioOrchestrationService(uow)
    orch.run(
        novabank_tenant,
        scenario_version_id=seeded_novabank["scenarios"]["version_ids"][0],
        as_of_at=AS_OF,
    )
    uow.commit()

    # Fresh session verification.
    engine = db_session.get_bind()
    fresh = Session(engine)
    try:
        after_owner_ids = sorted(
            o.ownership_id for o in fresh.scalars(select(ent_orm.Ownership)).all()
        )
        after_node_ids = sorted(
            n.graph_node_id for n in fresh.scalars(select(graph_orm.DeliveryGraphNode)).all()
        )
        after_edge_ids = sorted(
            e.graph_edge_id for e in fresh.scalars(select(graph_orm.DeliveryGraphEdge)).all()
        )
        after_snap_ids = sorted(
            s.prediction_feature_snapshot_id
            for s in fresh.scalars(select(pred_orm.PredictionFeatureSnapshot)).all()
        )
        after_pred_ids = sorted(
            p.delivery_prediction_id
            for p in fresh.scalars(select(pred_orm.DeliveryPrediction)).all()
        )
        assert after_owner_ids == before_owner_ids
        assert after_node_ids == before_node_ids
        assert after_edge_ids == before_edge_ids
        # Baseline extraction may create feature snapshots — that is observed data,
        # not scenario overlay mutation of existing snapshots' values.
        assert set(before_snap_ids).issubset(set(after_snap_ids))
        assert after_pred_ids == before_pred_ids
    finally:
        fresh.close()


def test_watch_no_change_then_relevant_change(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][0]
    watch = orch.create_watch(novabank_tenant, scenario_version_id=version_id)
    first = orch.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
    assert first.action == ScenarioTriggerAction.EVALUATED
    uow.commit()

    uow2 = UnitOfWork(db_session)
    orch2 = ScenarioOrchestrationService(uow2)
    # Force next_eligible into the past for interval bypass while testing fingerprint.
    watch_row = uow2.scenario_watches.require(novabank_tenant, watch.scenario_watch_id)
    from app.db.models import scenario_intelligence as sorm

    row = db_session.get(sorm.ScenarioWatch, watch_row.scenario_watch_id)
    assert row is not None
    row.next_eligible_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db_session.flush()
    second = orch2.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
    assert second.action == ScenarioTriggerAction.SKIPPED_NO_CHANGE
    uow2.commit()

    # Relevant ownership change — must affect the watch target neighborhood.
    from app.services.scenarios.fingerprints import compute_source_fingerprint

    version = uow2.scenario_versions.require(novabank_tenant, version_id)
    definition = uow2.scenario_definitions.require(novabank_tenant, version.scenario_definition_id)
    baseline_fp = compute_source_fingerprint(
        uow2,
        novabank_tenant,
        target_type=definition.target_type,
        target_id=definition.target_id,
        as_of_at=AS_OF,
        horizon_days=90,
        scenario_version_hash=version.specification_hash,
    )
    relevant = None
    for ownership in db_session.scalars(select(ent_orm.Ownership)).all():
        original = ownership.allocation
        ownership.allocation = 42 if original != 42 else 43
        db_session.flush()
        probe = compute_source_fingerprint(
            UnitOfWork(db_session),
            novabank_tenant,
            target_type=definition.target_type,
            target_id=definition.target_id,
            as_of_at=AS_OF,
            horizon_days=90,
            scenario_version_hash=version.specification_hash,
        )
        ownership.allocation = original
        db_session.flush()
        if probe.fingerprint != baseline_fp.fingerprint:
            relevant = ownership
            break
    assert relevant is not None
    relevant.allocation = 42 if relevant.allocation != 42 else 43
    db_session.commit()

    # Use an independent session after commit to avoid SQLite session residue.
    engine = db_session.get_bind()
    fresh = Session(engine)
    try:
        uow3 = UnitOfWork(fresh)
        orch3 = ScenarioOrchestrationService(uow3)
        from app.db.models import scenario_intelligence as sorm

        row = fresh.get(sorm.ScenarioWatch, watch.scenario_watch_id)
        assert row is not None
        row.next_eligible_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        fresh.flush()
        third = orch3.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
        assert third.action == ScenarioTriggerAction.EVALUATED, (
            third.trigger.sanitized_error_summary if third.trigger else third.action
        )
        uow3.commit()
    finally:
        fresh.close()


def test_comparison_and_cross_tenant_denial(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext, tenant_b: TenantContext
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    v1 = seeded_novabank["scenarios"]["version_ids"][1]
    # Use two runs against same target/as_of where possible; otherwise run two versions
    # for payment modernization initiative scenarios (indexes 1 and 2).
    b0 = orch.run(novabank_tenant, scenario_version_id=v1, as_of_at=AS_OF)
    b1 = orch.run(
        novabank_tenant,
        scenario_version_id=seeded_novabank["scenarios"]["version_ids"][2],
        as_of_at=AS_OF,
    )
    uow.commit()
    assert b0.result and b1.result
    # Same initiative target for platform capacity and shared repo scenarios.
    comparison = orch.compare(
        novabank_tenant,
        [b0.run.scenario_run_id, b1.run.scenario_run_id],
        sort_dimension=ComparisonDimension.AFFECTED_CRITICAL_INITIATIVE_COUNT,
    )
    assert len(comparison.ordered_run_ids) == 2

    foreign = uow.scenario_definitions.get(
        tenant_b, seeded_novabank["scenarios"]["definition_ids"][0]
    )
    assert foreign is None
    foreign_run = uow.scenario_runs.get(tenant_b, b0.run.scenario_run_id)
    assert foreign_run is None


def test_api_read_and_no_mutation_routes(seeded_novabank, client, novabank_tenant: TenantContext):
    headers = {"X-SignalForge-Tenant-ID": novabank_tenant.tenant_id}
    listed = client.get("/api/v3/scenarios", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 8
    health = client.get("/api/v3/scenarios/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["training_eligible_overlay_count"] == 0

    # Foreign tenant non-disclosure
    foreign = client.get(
        f"/api/v3/scenarios/{seeded_novabank['scenarios']['definition_ids'][0]}",
        headers={"X-SignalForge-Tenant-ID": "tenant-b"},
    )
    assert foreign.status_code == 404

    # No public mutation/execution endpoints
    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]
    scenario_paths = {
        p: methods for p, methods in paths.items() if p.startswith("/api/v3/scenarios")
    }
    for methods in scenario_paths.values():
        for method in methods:
            assert method.lower() in {"get", "head", "options"}
