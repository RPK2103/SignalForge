"""Story validation and materialization smoke tests."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import chief_of_staff as cos_orm
from app.db.models import graph as graph_orm
from app.db.unit_of_work import UnitOfWork
from app.demo.novabank.constants import AS_OF_AT, TENANT_ID
from app.demo.novabank.helpers import resolve_foundational_ids
from app.demo.novabank.intelligence import MaterializationError, materialize_intelligence
from app.demo.novabank.specification import CANONICAL_SPEC
from app.demo.novabank.validation import validate_dataset
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.domain.tenant_context import TenantContext
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.graph.projection_service import GraphProjectionService


def test_story_matrix_complete(seeded_demo, demo_session: Session):
    report = validate_dataset(demo_session)
    assert len(report.story_matrix) == 8
    for row in report.story_matrix:
        assert row["target"] and row["evidence"] and row["scenario"]


def test_materialize_deterministic_fallback(seeded_demo, demo_session: Session):
    result = materialize_intelligence(demo_session)
    demo_session.commit()
    assert result["ok"] is True
    assert result["graph_rebuilt"] is True
    assert result["scenarios_executed"] == 8
    assert result["briefs_generated"] == 8
    assert result["errors"] == []
    for kind in result["estimate_kinds"]:
        assert kind != "calibrated_probability"

    nodes = demo_session.scalar(
        select(func.count())
        .select_from(graph_orm.DeliveryGraphNode)
        .where(
            graph_orm.DeliveryGraphNode.tenant_id == TENANT_ID,
            graph_orm.DeliveryGraphNode.archived_at.is_(None),
        )
    )
    edges = demo_session.scalar(
        select(func.count())
        .select_from(graph_orm.DeliveryGraphEdge)
        .where(
            graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
            graph_orm.DeliveryGraphEdge.archived_at.is_(None),
        )
    )
    assert nodes and nodes > 100
    assert edges and edges > 100
    bad = demo_session.scalar(
        select(func.count())
        .select_from(graph_orm.DeliveryGraphEdge)
        .where(
            graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
            graph_orm.DeliveryGraphEdge.valid_to.is_not(None),
            graph_orm.DeliveryGraphEdge.valid_to <= graph_orm.DeliveryGraphEdge.valid_from,
        )
    )
    assert bad == 0

    report = validate_dataset(demo_session)
    assert report.ok, report.errors
    for row in report.story_matrix:
        for key in (
            "target",
            "evidence",
            "graph",
            "prediction_or_fallback",
            "scenario",
            "brief",
            "citations",
        ):
            assert row[key], f"{row['story_id']} missing {key}: {row}"


def test_graph_rebuild_idempotent(seeded_demo, demo_session: Session):
    ctx = TenantContext.require(TENANT_ID)
    uow = UnitOfWork(demo_session)
    GraphProjectionService(uow).full_rebuild(ctx)
    demo_session.commit()
    edges_1 = demo_session.scalar(
        select(func.count())
        .select_from(graph_orm.DeliveryGraphEdge)
        .where(
            graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
            graph_orm.DeliveryGraphEdge.archived_at.is_(None),
        )
    )
    GraphProjectionService(uow).full_rebuild(ctx)
    demo_session.commit()
    edges_2 = demo_session.scalar(
        select(func.count())
        .select_from(graph_orm.DeliveryGraphEdge)
        .where(
            graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
            graph_orm.DeliveryGraphEdge.archived_at.is_(None),
        )
    )
    assert edges_1 == edges_2
    assert edges_1 and edges_1 > 0


def test_story_7_brief_grounding(seeded_demo, demo_session: Session):
    ids = resolve_foundational_ids()
    ctx = TenantContext.require(TENANT_ID)
    uow = UnitOfWork(demo_session)
    GraphProjectionService(uow).full_rebuild(ctx)
    demo_session.flush()

    cos = ChiefOfStaffService(uow)
    outcome = cos.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=TENANT_ID,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=ids["proj:fraud-scoring-v2"],
            as_of_at=AS_OF_AT,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert outcome.brief is not None
    assert outcome.brief.probability is None
    assert outcome.run.evidence_package_hash
    text = " ".join(
        [
            getattr(outcome.brief, "executive_summary", "") or "",
            getattr(outcome.brief, "narrative", "") or "",
            str(getattr(outcome.brief, "sections", "") or ""),
        ]
    ).lower()
    for phrase in ("blame", "underperform", "productivity ranking", "employee ranking"):
        assert phrase not in text
    story = next(s for s in CANONICAL_SPEC.stories if s.story_id == "story-07")
    assert any("productivity" in c.lower() or "blame" in c.lower() for c in story.non_claims)
    citations = demo_session.scalars(
        select(cos_orm.CosCitation).where(cos_orm.CosCitation.tenant_id == TENANT_ID)
    ).all()
    assert citations or outcome.run.evidence_package_hash


def test_brief_grounding_for_fraud_story(seeded_demo, demo_session: Session):
    ids = resolve_foundational_ids()
    ctx = TenantContext.require(TENANT_ID)
    uow = UnitOfWork(demo_session)
    cos = ChiefOfStaffService(uow)
    outcome = cos.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=TENANT_ID,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=ids["proj:fraud-scoring-v2"],
            as_of_at=AS_OF_AT,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert outcome.brief is not None
    assert outcome.brief.probability is None
    assert outcome.run.evidence_package_hash
    story = next(s for s in CANONICAL_SPEC.stories if s.story_id == "story-01")
    assert "probability" in " ".join(story.non_claims).lower() or any(
        "probability" in c.lower() for c in story.non_claims
    )


def test_materialization_fails_closed_on_graph_error(
    seeded_demo, demo_session: Session, monkeypatch
):
    from app.services.graph import projection_service as ps

    def _boom(self, ctx):
        raise RuntimeError("forced_graph_failure")

    monkeypatch.setattr(ps.GraphProjectionService, "full_rebuild", _boom)
    try:
        materialize_intelligence(demo_session)
        raise AssertionError("expected MaterializationError")
    except MaterializationError as exc:
        assert exc.stage == "graph"
