"""Feature extraction tests for delivery prediction."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_enums import PredictionTargetType
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.prediction.feature_schema import FEATURE_NAMES

AS_OF = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
_LEAKAGE_FIELDS = {
    "binary_label",
    "outcome_category",
    "actual_completed_at",
    "probability_of_delivery_success",
}


def _project_id() -> str:
    return build_entity_id("proj", "novabank", "rt-payments-rail")


def test_deterministic_extract_same_hash_twice(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        extractor = FeatureExtractor(uow)
        a = extractor.extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        uow.commit()
        b = extractor.extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        assert a.feature_hash == b.feature_hash
        assert len(a.feature_hash) == 64
        assert a.prediction_feature_snapshot_id == b.prediction_feature_snapshot_id
    engine.dispose()


def test_no_target_leakage_fields(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        snap = FeatureExtractor(UnitOfWork(session)).extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        for name in _LEAKAGE_FIELDS:
            assert name not in snap.feature_values
            assert name not in snap.missingness_indicators
    engine.dispose()


def test_missingness_indicators_present(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        snap = FeatureExtractor(UnitOfWork(session)).extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        assert set(snap.missingness_indicators.keys()) == set(FEATURE_NAMES)
        for flag in snap.missingness_indicators.values():
            assert flag in (0, 1)
    engine.dispose()


def test_evidence_cutoff_le_as_of(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        snap = FeatureExtractor(UnitOfWork(session)).extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        assert snap.evidence_cutoff_at <= snap.as_of_at
        assert snap.as_of_at == AS_OF
    engine.dispose()


def test_work_item_post_cutoff_completion_stays_open_at_historical_cutoff(
    projected_novabank, novabank_tenant
):
    """Post-cutoff status=done must not shrink historical open_work_item_count."""
    from app.db.models import enterprise as ent_orm
    from app.services.prediction.feature_extractor import _work_item_state_at_cutoff

    assert (
        _work_item_state_at_cutoff(
            "done",
            AS_OF.replace(year=2025, month=7),  # completed after cutoff
            AS_OF,
        )
        == "open"
    )
    assert _work_item_state_at_cutoff("done", None, AS_OF) == "open"
    assert _work_item_state_at_cutoff("done", AS_OF, AS_OF) == "done"

    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        extractor = FeatureExtractor(uow)
        before = extractor.extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        open_before = before.feature_values.get("open_work_item_count")
        sprint_before = before.feature_values.get("sprint_completion_ratio")

        # Mutate current state: mark in-scope work items done AFTER the cutoff.
        work_items = list(
            session.scalars(
                select(ent_orm.WorkItem).where(
                    ent_orm.WorkItem.tenant_id == novabank_tenant.tenant_id,
                    ent_orm.WorkItem.enterprise_project_id == _project_id(),
                )
            ).all()
        )
        post = AS_OF.replace(month=8)
        mutated = 0
        for wi in work_items:
            if (
                wi.completed_at is None
                or (
                    wi.completed_at.replace(tzinfo=timezone.utc)
                    if wi.completed_at.tzinfo is None
                    else wi.completed_at
                )
                > AS_OF
            ):
                wi.status = "done"
                wi.completed_at = post
                mutated += 1
        assert mutated >= 1
        session.flush()

        after = extractor.extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        assert after.feature_values.get("open_work_item_count") == open_before
        assert after.feature_values.get("sprint_completion_ratio") == sprint_before
    engine.dispose()


def test_stale_source_ignores_mutable_freshness_state(projected_novabank, novabank_tenant):
    from app.db.models import enterprise as ent_orm

    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        extractor = FeatureExtractor(uow)
        before = extractor.extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        stale_before = before.feature_values.get("stale_source_count")

        for src in session.scalars(
            select(ent_orm.DataSource).where(
                ent_orm.DataSource.tenant_id == novabank_tenant.tenant_id
            )
        ).all():
            src.freshness_state = "stale"
        session.flush()

        after = extractor.extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        assert after.feature_values.get("stale_source_count") == stale_before
    engine.dispose()
