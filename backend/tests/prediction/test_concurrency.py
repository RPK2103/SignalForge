"""Concurrency / single-active invariant tests for delivery prediction."""

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_enums import ModelState
from app.domain.prediction_models import PredictionModel
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.orchestration import PredictionOrchestrationService
from app.services.prediction.registry import PredictionModelRegistry


def _validated_pair(uow: UnitOfWork, tenant):
    orch = PredictionOrchestrationService(uow)
    manifest = orch.build_dataset(tenant)
    first = orch.train(tenant, manifest.prediction_dataset_manifest_id, seed=42)
    first.model_state = ModelState.VALIDATED
    first = uow.prediction_models.update(tenant, first)

    payload = deepcopy(first.parameter_payload)
    payload["clone_marker"] = "concurrency_b"
    parameter_hash = snapshot_hash(payload)
    second = PredictionModel(
        tenant_id=first.tenant_id,
        prediction_model_id=f"{first.prediction_model_id[:50]}_c"[:64],
        model_name=first.model_name,
        model_type=first.model_type,
        model_version=f"v1-{parameter_hash[:12]}",
        target_definition=first.target_definition,
        horizon_days=first.horizon_days,
        feature_schema_version=first.feature_schema_version,
        label_version=first.label_version,
        dataset_manifest_id=first.dataset_manifest_id,
        training_code_version=first.training_code_version,
        parameter_payload=payload,
        parameter_hash=parameter_hash,
        training_seed=first.training_seed,
        trained_at=datetime.now(timezone.utc),
        model_state=ModelState.VALIDATED,
        usage_scope=first.usage_scope,
        data_scope=first.data_scope,
        production_eligible=False,
        created_at=datetime.now(timezone.utc),
    )
    second = uow.prediction_models.insert(tenant, second)
    uow.commit()
    return first, second


def test_two_sessions_promote_only_one_active(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as setup:
        first, second = _validated_pair(UnitOfWork(setup), novabank_tenant)
        first_id = first.prediction_model_id
        second_id = second.prediction_model_id
    engine.dispose()

    reset_engine()
    init_engine(projected_novabank)
    engine = get_engine(projected_novabank)

    with Session(engine) as session_a, Session(engine) as session_b:
        reg_a = PredictionModelRegistry(UnitOfWork(session_a))
        reg_b = PredictionModelRegistry(UnitOfWork(session_b))
        try:
            reg_a.promote(novabank_tenant, first_id, confirm=True)
            session_a.commit()
        except Exception:  # noqa: BLE001 - capture race outcomes
            session_a.rollback()
        try:
            reg_b.promote(novabank_tenant, second_id, confirm=True)
            session_b.commit()
        except Exception:  # noqa: BLE001 - capture race outcomes
            session_b.rollback()

    with Session(engine) as session:
        uow = UnitOfWork(session)
        actives = PredictionModelRegistry(uow).list(
            novabank_tenant, state=ModelState.ACTIVE, horizon_days=90, limit=20
        )
        assert len(actives) == 1
        # At least one promotion should have succeeded.
        assert actives[0].prediction_model_id in {first_id, second_id}
    engine.dispose()
