"""Audit regression tests for Prompt 5 fingerprint, concurrency, training, and bounds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import enterprise as ent_orm
from app.db.models import scenario_intelligence as sorm
from app.db.unit_of_work import UnitOfWork
from app.domain.scenario_enums import ScenarioTriggerAction
from app.domain.tenant_context import TenantContext
from app.services.scenarios.fingerprints import compute_source_fingerprint
from app.services.scenarios.orchestration import ScenarioOrchestrationService
from tests.scenarios.conftest import AS_OF


def _force_eligible(session: Session, watch_id: str) -> None:
    row = session.get(sorm.ScenarioWatch, watch_id)
    assert row is not None
    row.next_eligible_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    session.flush()


def test_as_of_wall_clock_does_not_change_source_fingerprint(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    uow = UnitOfWork(db_session)
    version_id = seeded_novabank["scenarios"]["version_ids"][0]
    version = uow.scenario_versions.require(novabank_tenant, version_id)
    definition = uow.scenario_definitions.require(novabank_tenant, version.scenario_definition_id)
    t1 = AS_OF
    t2 = AS_OF + timedelta(minutes=7)
    fp1 = compute_source_fingerprint(
        uow,
        novabank_tenant,
        target_type=definition.target_type,
        target_id=definition.target_id,
        as_of_at=t1,
        horizon_days=90,
        scenario_version_hash=version.specification_hash,
    )
    fp2 = compute_source_fingerprint(
        uow,
        novabank_tenant,
        target_type=definition.target_type,
        target_id=definition.target_id,
        as_of_at=t2,
        horizon_days=90,
        scenario_version_hash=version.specification_hash,
    )
    assert fp1.fingerprint == fp2.fingerprint
    assert fp1.components == fp2.components


def test_irrelevant_ownership_skips_and_relevant_triggers(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    # Fraud initiative watch — ownership on an out-of-scope resource must skip.
    version_id = seeded_novabank["scenarios"]["version_ids"][0]
    watch = orch.create_watch(novabank_tenant, scenario_version_id=version_id)
    first = orch.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
    assert first.action == ScenarioTriggerAction.EVALUATED
    uow.commit()

    version = uow.scenario_versions.require(novabank_tenant, version_id)
    definition = uow.scenario_definitions.require(novabank_tenant, version.scenario_definition_id)
    scope_fp = compute_source_fingerprint(
        uow,
        novabank_tenant,
        target_type=definition.target_type,
        target_id=definition.target_id,
        as_of_at=AS_OF,
        horizon_days=90,
        scenario_version_hash=version.specification_hash,
    )
    ownerships = list(db_session.scalars(select(ent_orm.Ownership)).all())
    assert ownerships

    irrelevant = None
    relevant = None
    for ownership in ownerships:
        original = ownership.allocation
        probe = 10 if original != 10 else 20
        ownership.allocation = probe
        db_session.flush()
        uow_probe = UnitOfWork(db_session)
        fp = compute_source_fingerprint(
            uow_probe,
            novabank_tenant,
            target_type=definition.target_type,
            target_id=definition.target_id,
            as_of_at=AS_OF,
            horizon_days=90,
            scenario_version_hash=version.specification_hash,
        )
        ownership.allocation = original
        db_session.flush()
        if fp.fingerprint == scope_fp.fingerprint and irrelevant is None:
            irrelevant = ownership.ownership_id
        if fp.fingerprint != scope_fp.fingerprint and relevant is None:
            relevant = ownership.ownership_id
        if irrelevant and relevant:
            break
    assert irrelevant is not None, "expected at least one out-of-scope ownership"
    assert relevant is not None, "expected at least one in-scope ownership"

    irr = db_session.get(ent_orm.Ownership, irrelevant)
    assert irr is not None
    irr.allocation = 10 if irr.allocation != 10 else 20
    db_session.commit()

    fresh = Session(db_session.get_bind())
    try:
        orch2 = ScenarioOrchestrationService(UnitOfWork(fresh))
        _force_eligible(fresh, watch.scenario_watch_id)
        second = orch2.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
        assert second.action == ScenarioTriggerAction.SKIPPED_NO_CHANGE
        orch2._uow.commit()
    finally:
        fresh.close()

    fresh2 = Session(db_session.get_bind())
    try:
        rel = fresh2.get(ent_orm.Ownership, relevant)
        assert rel is not None
        rel.allocation = 30 if rel.allocation != 30 else 40
        fresh2.commit()
    finally:
        fresh2.close()

    fresh3 = Session(db_session.get_bind())
    try:
        orch3 = ScenarioOrchestrationService(UnitOfWork(fresh3))
        _force_eligible(fresh3, watch.scenario_watch_id)
        third = orch3.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
        assert third.action == ScenarioTriggerAction.EVALUATED
        orch3._uow.commit()
    finally:
        fresh3.close()


def test_failed_watch_does_not_advance_fingerprint(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext, monkeypatch
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][0]
    watch = orch.create_watch(novabank_tenant, scenario_version_id=version_id)
    first = orch.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
    assert first.action == ScenarioTriggerAction.EVALUATED
    prior_fp = first.watch.last_source_fingerprint
    prior_hash = first.watch.last_result_hash
    uow.commit()

    from app.services.scenarios import watches as watches_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("injected_failure_after_trigger")

    monkeypatch.setattr(watches_mod.ScenarioExecutionService, "execute", _boom)

    fresh = Session(db_session.get_bind())
    try:
        orch2 = ScenarioOrchestrationService(UnitOfWork(fresh))
        _force_eligible(fresh, watch.scenario_watch_id)
        # force=True bypasses no-change short-circuit so execution failure is reached.
        result = orch2.evaluate_watch(
            novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF, force=True
        )
        assert result.action == ScenarioTriggerAction.FAILED
        assert result.watch.last_source_fingerprint == prior_fp
        assert result.watch.last_result_hash == prior_hash
        orch2._uow.commit()
    finally:
        fresh.close()


def test_concurrent_watch_evaluation_single_result(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    """Optimistic lock CAS prevents duplicate watch evaluation ownership.

    Independent sessions prove compare-and-swap. A second evaluator with a stale
    lock_version is rejected. SQLite file locking limits true parallel writers;
    this is not a PostgreSQL concurrency guarantee.
    """
    engine = db_session.get_bind()
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    version_id = seeded_novabank["scenarios"]["version_ids"][1]
    watch = orch.create_watch(novabank_tenant, scenario_version_id=version_id)
    uow.commit()

    s1 = Session(engine)
    s2 = Session(engine)
    try:
        w1 = UnitOfWork(s1).scenario_watches.require(novabank_tenant, watch.scenario_watch_id)
        locked = UnitOfWork(s1).scenario_watches.try_acquire_lock(
            novabank_tenant, watch.scenario_watch_id, w1.lock_version
        )
        assert locked is not None
        assert locked.lock_version == w1.lock_version + 1
        s1.commit()

        contested = UnitOfWork(s2).scenario_watches.try_acquire_lock(
            novabank_tenant, watch.scenario_watch_id, w1.lock_version
        )
        assert contested is None

        # Fresh read sees advanced lock; acquire with current version succeeds.
        current = UnitOfWork(s2).scenario_watches.require(novabank_tenant, watch.scenario_watch_id)
        again = UnitOfWork(s2).scenario_watches.try_acquire_lock(
            novabank_tenant, watch.scenario_watch_id, current.lock_version
        )
        assert again is not None
        s2.commit()
    finally:
        s1.close()
        s2.close()

    # Evaluate once; a second identical evaluation must reuse / skip rather than
    # create a second succeeded run input hash.
    fresh = Session(engine)
    try:
        local = ScenarioOrchestrationService(UnitOfWork(fresh))
        _force_eligible(fresh, watch.scenario_watch_id)
        first = local.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
        local._uow.commit()
        assert first.action == ScenarioTriggerAction.EVALUATED
    finally:
        fresh.close()

    fresh2 = Session(engine)
    try:
        local2 = ScenarioOrchestrationService(UnitOfWork(fresh2))
        _force_eligible(fresh2, watch.scenario_watch_id)
        second = local2.evaluate_watch(novabank_tenant, watch.scenario_watch_id, as_of_at=AS_OF)
        local2._uow.commit()
        assert second.action == ScenarioTriggerAction.SKIPPED_NO_CHANGE
    finally:
        fresh2.close()

    verify = Session(engine)
    try:
        runs = verify.scalars(
            select(sorm.ScenarioRun).where(
                sorm.ScenarioRun.tenant_id == novabank_tenant.tenant_id,
                sorm.ScenarioRun.scenario_version_id == version_id,
                sorm.ScenarioRun.state == "succeeded",
            )
        ).all()
        assert len({r.run_input_hash for r in runs}) == 1
    finally:
        verify.close()


def test_training_eligible_sql_bypass_rejected(
    seeded_novabank, db_session: Session, novabank_tenant: TenantContext
):
    uow = UnitOfWork(db_session)
    orch = ScenarioOrchestrationService(uow)
    bundle = orch.run(
        novabank_tenant,
        scenario_version_id=seeded_novabank["scenarios"]["version_ids"][0],
        as_of_at=AS_OF,
    )
    uow.commit()
    assert bundle.feature_overlay is not None
    overlay_id = bundle.feature_overlay.scenario_feature_overlay_id

    with pytest.raises(Exception):
        db_session.execute(
            text(
                "UPDATE ent_scenario_feature_overlays "
                "SET training_eligible = 1 "
                "WHERE scenario_feature_overlay_id = :oid"
            ),
            {"oid": overlay_id},
        )
        db_session.commit()
    db_session.rollback()

    row = db_session.get(sorm.ScenarioFeatureOverlay, overlay_id)
    assert row is not None
    assert int(row.training_eligible) == 0


def test_dataset_builder_does_not_reference_scenario_overlays():
    builder = Path("app/services/prediction/dataset_builder.py").read_text(encoding="utf-8")
    assert "ScenarioFeatureOverlay" not in builder
    assert "scenario_feature_overlay" not in builder
    assert "ent_scenario_feature_overlays" not in builder
