"""Dataset builder tests for delivery prediction."""

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import (
    DEFAULT_HORIZON_DAYS,
    MIN_LABELED_ROWS,
    MIN_NEGATIVE_ROWS,
    MIN_POSITIVE_ROWS,
)
from app.domain.prediction_enums import OutcomeCategory
from app.services.prediction.dataset_builder import PredictionDatasetBuilder
from app.services.prediction.orchestration import PredictionOrchestrationService


def test_build_on_projected_novabank(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        health = orch.data_health(novabank_tenant)
        assert health.labeled_outcomes >= MIN_LABELED_ROWS
        assert health.positive_outcomes >= MIN_POSITIVE_ROWS
        assert health.negative_outcomes >= MIN_NEGATIVE_ROWS
        assert health.censored_outcomes >= 1

        manifest = orch.build_dataset(novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS)
        uow.commit()

        assert manifest.labeled_rows >= MIN_LABELED_ROWS
        assert manifest.positive_rows >= MIN_POSITIVE_ROWS
        assert manifest.negative_rows >= MIN_NEGATIVE_ROWS
        assert manifest.censored_rows >= 1
        assert manifest.sufficiency_passed is True
        assert len(manifest.dataset_hash) == 64

        # Temporal split order: train cutoffs should not be after test cutoffs on average
        # via grouped earliest-cutoff ordering — partitions are non-empty.
        assert len(manifest.train_row_ids) > 0
        assert len(manifest.calibration_row_ids) > 0
        assert len(manifest.test_row_ids) > 0

        train_set = set(manifest.train_row_ids)
        cal_set = set(manifest.calibration_row_ids)
        test_set = set(manifest.test_row_ids)
        assert train_set.isdisjoint(cal_set)
        assert train_set.isdisjoint(test_set)
        assert cal_set.isdisjoint(test_set)

        # Censored outcomes excluded from labeled partitions.
        for oid in list(train_set | cal_set | test_set)[:20]:
            outcome = uow.delivery_outcomes.get(novabank_tenant, oid)
            assert outcome is not None
            assert outcome.outcome_category not in {
                OutcomeCategory.CENSORED,
                OutcomeCategory.UNKNOWN,
            }
            assert outcome.binary_label in (0, 1)
    engine.dispose()


def test_stable_dataset_hash_on_rebuild(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        builder = PredictionDatasetBuilder(uow)
        first = builder.build(novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS)
        uow.commit()
        second = builder.build(novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS)
        uow.commit()
        assert first.dataset_hash == second.dataset_hash
        assert first.prediction_dataset_manifest_id == second.prediction_dataset_manifest_id
        assert first.train_row_ids_hash == second.train_row_ids_hash
        assert first.calibration_row_ids_hash == second.calibration_row_ids_hash
        assert first.test_row_ids_hash == second.test_row_ids_hash
    engine.dispose()


def test_grouped_split_no_outcome_id_in_multiple_partitions(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        manifest = PredictionDatasetBuilder(uow).build(
            novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS
        )
        uow.commit()
        all_ids = (
            list(manifest.train_row_ids)
            + list(manifest.calibration_row_ids)
            + list(manifest.test_row_ids)
        )
        assert len(all_ids) == len(set(all_ids))

        # Whole target groups stay in one partition.
        def partition_of(oid: str) -> str:
            if oid in manifest.train_row_ids:
                return "train"
            if oid in manifest.calibration_row_ids:
                return "cal"
            return "test"

        groups: dict[tuple[str, str], set[str]] = {}
        for oid in all_ids:
            outcome = uow.delivery_outcomes.get(novabank_tenant, oid)
            assert outcome is not None
            key = (
                outcome.target_type.value
                if hasattr(outcome.target_type, "value")
                else str(outcome.target_type),
                outcome.target_id,
            )
            groups.setdefault(key, set()).add(partition_of(oid))
        for parts in groups.values():
            assert len(parts) == 1
    engine.dispose()
