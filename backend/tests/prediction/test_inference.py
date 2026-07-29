"""Inference tests for delivery prediction."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import (
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    MAX_FACTORS,
)
from app.domain.prediction_enums import EstimateKind, PredictionTargetType
from app.services.enterprise.exceptions import EnterpriseNotFoundError
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.baseline import DeliveryScorecardV1
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.prediction.orchestration import PredictionOrchestrationService

AS_OF = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


def _project_id() -> str:
    return build_entity_id("proj", "novabank", "rt-payments-rail")


def test_fallback_uncalibrated_without_active_model(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        active = orch.registry.list(novabank_tenant, state=None, limit=50)
        assert not any(m.model_state.value == "active" for m in active)

        bundle = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=AS_OF,
            horizon_days=DEFAULT_HORIZON_DAYS,
        )
        uow.commit()
        assert bundle.prediction.estimate_kind == EstimateKind.UNCALIBRATED_SCORE
        assert bundle.prediction.probability_of_delivery_success is None
        assert bundle.prediction.uncalibrated_risk_score is not None
        assert 0.0 <= bundle.prediction.uncalibrated_risk_score <= 100.0
        assert "baseline_fallback" in bundle.prediction.data_quality_warnings
    engine.dispose()


def test_prediction_hash_stable_for_same_as_of(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        a = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=AS_OF,
        )
        uow.commit()
        assert len(a.prediction.prediction_hash) == 64

        # Idempotent re-predict: same inputs return the same immutable prediction.
        b = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=AS_OF,
        )
        uow.commit()
        assert b.prediction.prediction_hash == a.prediction.prediction_hash
        assert b.prediction.delivery_prediction_id == a.prediction.delivery_prediction_id

        by_hash = uow.delivery_predictions.get_by_hash(
            novabank_tenant, a.prediction.prediction_hash
        )
        assert by_hash is not None
        assert by_hash.delivery_prediction_id == a.prediction.delivery_prediction_id

        # Recompute scorecard hash inputs independently and match.
        snap = FeatureExtractor(uow).extract(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            AS_OF,
        )
        scorecard = DeliveryScorecardV1().score(snap.feature_values, snap.missingness_indicators)
        body = {
            "tenant_id": novabank_tenant.tenant_id,
            "target_type": PredictionTargetType.PROJECT.value,
            "target_id": _project_id(),
            "as_of_at": AS_OF.isoformat(),
            "horizon_days": DEFAULT_HORIZON_DAYS,
            "estimate_kind": EstimateKind.UNCALIBRATED_SCORE.value,
            "uncalibrated_risk_score": float(scorecard.delivery_risk_score),
            "baseline_version": scorecard.scorecard_version,
            "feature_snapshot_id": snap.prediction_feature_snapshot_id,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        }
        assert snapshot_hash(body) == a.prediction.prediction_hash
    engine.dispose()


def test_factors_bounded_max_8(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        bundle = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=AS_OF,
        )
        uow.commit()
        assert len(bundle.factors) <= MAX_FACTORS
        for factor in bundle.factors:
            assert 1 <= factor.rank <= MAX_FACTORS
    engine.dispose()


def test_history_preserved(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        first = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=AS_OF,
        )
        second = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        uow.commit()
        history = uow.delivery_predictions.list_for_target(
            novabank_tenant,
            PredictionTargetType.PROJECT.value,
            _project_id(),
            limit=50,
        )
        ids = {item.delivery_prediction_id for item in history.items}
        assert first.prediction.delivery_prediction_id in ids
        assert second.prediction.delivery_prediction_id in ids
        assert history.total >= 2
    engine.dispose()


def test_unsupported_horizon_insufficient_or_error(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        bundle = orch.predict(
            novabank_tenant,
            PredictionTargetType.PROJECT,
            _project_id(),
            as_of_at=AS_OF,
            horizon_days=45,
        )
        uow.commit()
        assert bundle.prediction.estimate_kind == EstimateKind.INSUFFICIENT_DATA
        assert "unsupported_horizon" in bundle.prediction.data_quality_warnings
    engine.dispose()


def test_unresolved_target_raises_not_found(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        with pytest.raises(EnterpriseNotFoundError):
            orch.predict(
                novabank_tenant,
                PredictionTargetType.PROJECT,
                "proj_does_not_exist",
                as_of_at=AS_OF,
            )
    engine.dispose()
