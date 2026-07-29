"""Database A/B determinism and NovaBank scenario-comparison audit proofs."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.db.enterprise_seed import TENANT_ID as NOVABANK_TENANT_ID
from app.db.enterprise_seed import seed_enterprise
from app.db.models import enterprise as ent_orm
from app.db.models import graph as graph_orm
from app.db.models import prediction as pred_orm
from app.db.models import scenario_intelligence as scen_orm
from app.db.scenario_seed import seed_novabank_scenarios
from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.chief_of_staff_constants import (
    FALLBACK_TEMPLATE_VERSION,
    OUTPUT_SCHEMA_VERSION,
)
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.domain.tenant_context import TenantContext
from app.services.chief_of_staff.canonicalization import (
    attach_package_hash,
    compute_brief_output_hash,
)
from app.services.chief_of_staff.fallback import build_fallback_brief
from app.services.chief_of_staff.grounding import validate_brief_grounding
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.projection_service import GraphProjectionService
from app.services.scenarios.orchestration import ScenarioOrchestrationService

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _upgrade(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    command.upgrade(Config("alembic.ini"), "head")


def _seed_novabank(session: Session) -> TenantContext:
    seed_enterprise(session)
    session.commit()
    ctx = TenantContext.require(NOVABANK_TENANT_ID)
    uow = UnitOfWork(session)
    GraphProjectionService(uow).full_rebuild(ctx)
    GraphAnalysisService(uow).analyze(ctx)
    seed_novabank_scenarios(session)
    session.commit()
    return ctx


def _first_project(uow: UnitOfWork, ctx: TenantContext) -> str:
    page = uow.initiatives_projects.list_projects(ctx, limit=5, offset=0)
    assert page.items
    return page.items[0].enterprise_project_id


def test_database_a_b_output_hash_independent_of_persistence_ids(tmp_path: Path):
    """Same logical evidence in two DBs → same package_hash and output_hash."""
    url_a = f"sqlite:///{(tmp_path / 'db_a.db').as_posix()}"
    url_b = f"sqlite:///{(tmp_path / 'db_b.db').as_posix()}"

    _upgrade(url_a)
    engine_a = get_engine(url_a)
    session_a = Session(engine_a)
    ctx_a = _seed_novabank(session_a)
    uow_a = UnitOfWork(session_a)
    target_a = _first_project(uow_a, ctx_a)
    service_a = ChiefOfStaffService(uow_a)
    out_a = service_a.generate(
        ctx_a,
        ChiefOfStaffRequest(
            tenant_id=ctx_a.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_a,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    session_a.commit()

    reset_engine()
    get_settings.cache_clear()

    _upgrade(url_b)
    engine_b = get_engine(url_b)
    session_b = Session(engine_b)
    ctx_b = _seed_novabank(session_b)
    uow_b = UnitOfWork(session_b)
    session_b.flush()
    target_b = _first_project(uow_b, ctx_b)
    assert target_a == target_b
    service_b = ChiefOfStaffService(uow_b)
    out_b = service_b.generate(
        ctx_b,
        ChiefOfStaffRequest(
            tenant_id=ctx_b.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_b,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    session_b.commit()

    assert out_a.evidence_snapshot.snapshot_id != out_b.evidence_snapshot.snapshot_id
    assert out_a.run.run_id != out_b.run.run_id
    assert out_a.brief.brief_id != out_b.brief.brief_id

    assert out_a.package.package_hash == out_b.package.package_hash
    assert out_a.run.evidence_package_hash == out_b.run.evidence_package_hash
    assert out_a.run.output_hash == out_b.run.output_hash
    assert [c.claim_id for c in out_a.structured_brief.claims] == [
        c.claim_id for c in out_b.structured_brief.claims
    ]
    assert [c.text for c in out_a.structured_brief.claims] == [
        c.text for c in out_b.structured_brief.claims
    ]
    assert [c.ordering_index for c in out_a.structured_brief.claims] == [
        c.ordering_index for c in out_b.structured_brief.claims
    ]
    assert [c.citation_id for c in out_a.structured_brief.citations] == [
        c.citation_id for c in out_b.structured_brief.citations
    ]
    assert [c.evidence_id for c in out_a.structured_brief.citations] == [
        c.evidence_id for c in out_b.structured_brief.citations
    ]
    assert [c.ordering_index for c in out_a.structured_brief.citations] == [
        c.ordering_index for c in out_b.structured_brief.citations
    ]
    assert all(
        c.package_id == out_a.package.package_hash for c in out_a.structured_brief.citations
    )
    assert all(
        c.package_id == out_b.package.package_hash for c in out_b.structured_brief.citations
    )

    package_hash = out_a.package.package_hash
    output_hash = out_a.run.output_hash

    mutated = out_a.package.model_copy(
        update={
            "missing_data_warnings": sorted(
                list(out_a.package.missing_data_warnings) + ["audit-injected-warning"]
            ),
            "package_hash": "",
        }
    )
    mutated = attach_package_hash(mutated)
    assert mutated.package_hash != package_hash
    mutated_brief = build_fallback_brief(
        mutated, evidence_package_hash=mutated.package_hash
    )
    mutated_output = compute_brief_output_hash(
        mutated_brief, evidence_package_hash=mutated.package_hash
    )
    assert mutated_output != output_hash

    same_brief = build_fallback_brief(
        out_a.package, evidence_package_hash=out_a.package.package_hash
    )
    same_output = compute_brief_output_hash(
        same_brief, evidence_package_hash=out_a.package.package_hash
    )
    assert same_output == output_hash

    version_changed = compute_brief_output_hash(
        same_brief,
        evidence_package_hash=out_a.package.package_hash,
        fallback_template_version=FALLBACK_TEMPLATE_VERSION + "-audit",
        output_schema_version=OUTPUT_SCHEMA_VERSION,
    )
    assert version_changed != output_hash
    schema_changed = compute_brief_output_hash(
        same_brief,
        evidence_package_hash=out_a.package.package_hash,
        fallback_template_version=FALLBACK_TEMPLATE_VERSION,
        output_schema_version=OUTPUT_SCHEMA_VERSION + "-audit",
    )
    assert schema_changed != output_hash

    print("DB_A_PACKAGE_ID", out_a.evidence_snapshot.snapshot_id)
    print("DB_B_PACKAGE_ID", out_b.evidence_snapshot.snapshot_id)
    print("PACKAGE_HASH", package_hash)
    print("OUTPUT_HASH", output_hash)

    session_a.close()
    session_b.close()
    engine_a.dispose()
    engine_b.dispose()
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


def test_novabank_scenario_comparison_brief_proof(
    seeded_novabank, uow, novabank_tenant, db_session
):
    """Generate scenario_comparison_brief after ensuring two completed runs."""
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=50, offset=0)
    target = next(
        (p for p in projects.items if "rt-payments" in (p.slug or p.name).lower()),
        None,
    )
    assert target is not None, "expected NovaBank rt-payments-rail project"
    target_id = target.enterprise_project_id
    target_type = ChiefOfStaffTargetType.PROJECT

    defs = [
        d
        for d in uow.scenario_definitions.list(
            novabank_tenant, limit=100, offset=0, target_type="project", target_id=target_id
        ).items
    ]
    if len(defs) < 2:
        by_target: dict[tuple[str, str], list] = {}
        for d in uow.scenario_definitions.list(novabank_tenant, limit=100, offset=0).items:
            key = (
                d.target_type.value if hasattr(d.target_type, "value") else str(d.target_type),
                d.target_id,
            )
            by_target.setdefault(key, []).append(d)
        key, defs = next((k, v) for k, v in by_target.items() if len(v) >= 2)
        target_type = ChiefOfStaffTargetType(key[0])
        target_id = key[1]

    before_owners = sorted(
        o.ownership_id for o in db_session.scalars(select(ent_orm.Ownership)).all()
    )
    before_nodes = sorted(
        n.graph_node_id for n in db_session.scalars(select(graph_orm.DeliveryGraphNode)).all()
    )
    before_preds = sorted(
        p.delivery_prediction_id
        for p in db_session.scalars(select(pred_orm.DeliveryPrediction)).all()
    )
    before_runs = sorted(
        r.scenario_run_id for r in db_session.scalars(select(scen_orm.ScenarioRun)).all()
    )

    orch = ScenarioOrchestrationService(uow)
    run_ids: list[str] = []
    for definition in defs[:2]:
        versions = uow.scenario_versions.list_for_definition(
            novabank_tenant, definition.scenario_definition_id, limit=5, offset=0
        )
        assert versions.items
        version_id = versions.items[0].scenario_version_id
        bundle = orch.run(
            novabank_tenant, scenario_version_id=version_id, as_of_at=AS_OF
        )
        assert bundle.run is not None
        assert bundle.result is not None
        run_ids.append(bundle.run.scenario_run_id)
    uow.commit()
    assert len(set(run_ids)) == 2

    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF,
            target_type=target_type,
            target_id=target_id,
            as_of_at=AS_OF,
            scenario_run_ids=run_ids,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert outcome.brief is not None
    assert outcome.run.generation_state.value == "fallback_generated"
    assert outcome.run.final_provider == ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK
    assert outcome.structured_brief.probability is None
    validate_brief_grounding(
        outcome.structured_brief,
        outcome.package,
        evidence_package_hash=outcome.package.package_hash,
    )
    assert outcome.package.scenario_comparability is not None
    estimate_kinds = list(outcome.package.scenario_comparability.estimate_kinds)
    assert all(
        c.package_id == outcome.package.package_hash
        for c in outcome.structured_brief.citations
    )

    scenario_claims = [
        c
        for c in outcome.structured_brief.claims
        if c.claim_type.value == "scenario_implication" or "scenario" in c.text.lower()
    ]
    assert outcome.structured_brief.claims
    assert outcome.structured_brief.citations

    after_owners = sorted(
        o.ownership_id for o in db_session.scalars(select(ent_orm.Ownership)).all()
    )
    after_nodes = sorted(
        n.graph_node_id for n in db_session.scalars(select(graph_orm.DeliveryGraphNode)).all()
    )
    after_preds = sorted(
        p.delivery_prediction_id
        for p in db_session.scalars(select(pred_orm.DeliveryPrediction)).all()
    )
    after_runs = sorted(
        r.scenario_run_id for r in db_session.scalars(select(scen_orm.ScenarioRun)).all()
    )
    assert after_owners == before_owners
    assert after_nodes == before_nodes
    assert after_preds == before_preds
    assert set(before_runs).issubset(set(after_runs))
    assert set(run_ids).issubset(set(after_runs))

    print("TENANT", novabank_tenant.tenant_id)
    print("TARGET_TYPE", target_type.value)
    print("TARGET_ID", target_id)
    print("CUTOFF", AS_OF.isoformat())
    print("SCENARIO_RUN_IDS", run_ids)
    print("COS_RUN_ID", outcome.run.run_id)
    print("BRIEF_ID", outcome.brief.brief_id)
    print("REQUESTED_PROVIDER", outcome.run.requested_provider.value)
    print("FINAL_PROVIDER", outcome.run.final_provider.value)
    print("GENERATION_STATE", outcome.run.generation_state.value)
    print("ESTIMATE_KINDS", estimate_kinds)
    print("COMPARABILITY", outcome.package.scenario_comparability.model_dump(mode="json"))
    print("PROBABILITY", outcome.structured_brief.probability)
    print("EVIDENCE_HASH", outcome.package.package_hash)
    print("OUTPUT_HASH", outcome.run.output_hash)
    print("CLAIM_COUNT", len(outcome.structured_brief.claims))
    print("CITATION_COUNT", len(outcome.structured_brief.citations))
    print(
        "REPR_SCENARIO_CLAIMS",
        [
            (c.claim_id, c.text[:120], c.evidence_ids)
            for c in (scenario_claims or outcome.structured_brief.claims)[:5]
        ],
    )
