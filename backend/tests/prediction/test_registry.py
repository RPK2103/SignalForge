"""Model registry lifecycle tests for delivery prediction."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_enums import ModelState
from app.domain.prediction_models import PredictionModel
from app.security.context import internal_system_context
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.orchestration import PredictionOrchestrationService


def _validator_security(tenant_id: str = "novabank"):
    return internal_system_context(tenant_id, correlation_id="pred-registry-eval")


def _train_candidate(uow: UnitOfWork, tenant):
    orch = PredictionOrchestrationService(uow)
    manifest = orch.build_dataset(tenant)
    model = orch.train(tenant, manifest.prediction_dataset_manifest_id, seed=42)
    uow.commit()
    return orch, model


def _force_validated(uow: UnitOfWork, tenant, model):
    model.model_state = ModelState.VALIDATED
    return uow.prediction_models.update(tenant, model)


def _clone_validated_competitor(
    uow: UnitOfWork, tenant, source: PredictionModel
) -> PredictionModel:
    """Insert a second validated model in the same scope for promotion contests."""
    payload = deepcopy(source.parameter_payload)
    payload["clone_marker"] = "competitor_b"
    parameter_hash = snapshot_hash(payload)
    clone = PredictionModel(
        tenant_id=source.tenant_id,
        prediction_model_id=f"{source.prediction_model_id[:50]}_b"[:64],
        model_name=source.model_name,
        model_type=source.model_type,
        model_version=f"v1-{parameter_hash[:12]}",
        target_definition=source.target_definition,
        horizon_days=source.horizon_days,
        feature_schema_version=source.feature_schema_version,
        label_version=source.label_version,
        dataset_manifest_id=source.dataset_manifest_id,
        training_code_version=source.training_code_version,
        parameter_payload=payload,
        parameter_hash=parameter_hash,
        training_seed=source.training_seed,
        trained_at=datetime.now(timezone.utc),
        model_state=ModelState.VALIDATED,
        usage_scope=source.usage_scope,
        data_scope=source.data_scope,
        production_eligible=False,
        created_at=datetime.now(timezone.utc),
    )
    return uow.prediction_models.insert(tenant, clone)


def test_promote_without_confirm_fails(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        _force_validated(uow, novabank_tenant, model)
        uow.commit()
        with pytest.raises(ValueError, match="confirm=True"):
            orch.promote(novabank_tenant, model.prediction_model_id, confirm=False)
    engine.dispose()


def test_promote_unvalidated_fails(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        assert model.model_state == ModelState.CANDIDATE
        with pytest.raises(ValueError, match="validated"):
            orch.promote(novabank_tenant, model.prediction_model_id, confirm=True)
    engine.dispose()


def test_promote_when_validated_else_leave_candidate(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        evaluation = orch.evaluate(
            novabank_tenant,
            model.prediction_model_id,
            security=_validator_security(),
            mark_validated_if_passing=True,
        )
        uow.commit()
        refreshed = orch.registry.get(novabank_tenant, model.prediction_model_id)
        assert refreshed is not None

        if evaluation.passed_validation_gates:
            assert refreshed.model_state == ModelState.VALIDATED
            promoted = orch.promote(novabank_tenant, refreshed.prediction_model_id, confirm=True)
            uow.commit()
            assert promoted.model_state == ModelState.ACTIVE
            assert promoted.production_eligible is False
        else:
            assert refreshed.model_state == ModelState.CANDIDATE
            with pytest.raises(ValueError, match="validated"):
                orch.promote(novabank_tenant, refreshed.prediction_model_id, confirm=True)
    engine.dispose()


def test_retire_works(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        validated = _force_validated(uow, novabank_tenant, model)
        promoted = orch.promote(novabank_tenant, validated.prediction_model_id, confirm=True)
        uow.commit()
        assert promoted.model_state == ModelState.ACTIVE

        retired = orch.retire(novabank_tenant, promoted.prediction_model_id)
        uow.commit()
        assert retired.model_state == ModelState.RETIRED
        assert retired.retired_at is not None
        assert orch.registry.get_active(novabank_tenant, horizon_days=90) is None
    engine.dispose()


def test_competing_active_only_one(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, first = _train_candidate(uow, novabank_tenant)
        first = _force_validated(uow, novabank_tenant, first)
        second = _clone_validated_competitor(uow, novabank_tenant, first)
        uow.commit()
        assert first.prediction_model_id != second.prediction_model_id

        orch.promote(novabank_tenant, first.prediction_model_id, confirm=True)
        uow.commit()
        orch.promote(novabank_tenant, second.prediction_model_id, confirm=True)
        uow.commit()

        actives = orch.registry.list(
            novabank_tenant, state=ModelState.ACTIVE, horizon_days=90, limit=20
        )
        assert len(actives) == 1
        assert actives[0].prediction_model_id == second.prediction_model_id

        retired_first = orch.registry.get(novabank_tenant, first.prediction_model_id)
        assert retired_first is not None
        assert retired_first.model_state == ModelState.RETIRED
    engine.dispose()
