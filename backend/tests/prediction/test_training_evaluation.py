"""Training and evaluation tests for delivery prediction."""

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS
from app.domain.prediction_enums import ModelState
from app.services.prediction.orchestration import PredictionOrchestrationService


def test_train_evaluate_gates_no_auto_promote(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)

        manifest = orch.build_dataset(novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS)
        uow.commit()
        assert manifest.sufficiency_passed is True

        model = orch.train(novabank_tenant, manifest.prediction_dataset_manifest_id, seed=42)
        uow.commit()
        assert model.model_state == ModelState.CANDIDATE
        assert model.production_eligible is False
        assert model.promoted_at is None

        payload = model.parameter_payload
        assert "coefficients" in payload
        assert "intercept" in payload
        assert "calibration_slope" in payload
        assert "calibration_intercept" in payload
        assert isinstance(payload["coefficients"], list)
        assert len(payload["coefficients"]) > 0
        assert all(isinstance(c, float) for c in payload["coefficients"][:5])

        evaluation = orch.evaluate(novabank_tenant, model.prediction_model_id)
        uow.commit()
        assert evaluation.prediction_model_id == model.prediction_model_id
        assert evaluation.passed_validation_gates in (True, False)
        assert evaluation.row_count > 0

        refreshed = orch.registry.get(novabank_tenant, model.prediction_model_id)
        assert refreshed is not None
        # Default evaluate path does not auto-promote; remains candidate unless
        # mark_validated_if_passing flips state to validated (still not active).
        assert refreshed.model_state in {ModelState.CANDIDATE, ModelState.VALIDATED}
        assert refreshed.model_state != ModelState.ACTIVE
        assert refreshed.production_eligible is False
    engine.dispose()


def test_insufficient_history_empty_tenant(migrated_db, tenant_a):
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        health = orch.data_health(tenant_a)
        assert health.labeled_outcomes == 0
        assert "insufficient_labeled_outcomes" in health.warnings

        manifest = orch.build_dataset(tenant_a, horizon_days=DEFAULT_HORIZON_DAYS)
        uow.commit()
        assert manifest.sufficiency_passed is False
        assert manifest.labeled_rows == 0

        with pytest.raises(ValueError, match="sufficiency"):
            orch.train(tenant_a, manifest.prediction_dataset_manifest_id, seed=42)
    engine.dispose()


def test_train_rejects_manifest_without_explicit_leakage_check(projected_novabank, novabank_tenant):
    """Prebuilt/partial manifests missing leakage_clean must not train."""
    from app.db.models import prediction as pred_orm

    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        manifest = orch.build_dataset(novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS)
        uow.commit()

        # Simulate a prebuilt manifest that claims sufficiency without an
        # explicit leakage_clean check (trainer must refuse, not assume clean).
        row = session.get(
            pred_orm.PredictionDatasetManifest,
            manifest.prediction_dataset_manifest_id,
        )
        assert row is not None
        report = dict(row.sufficiency_report or {})
        checks = dict(report.get("checks") or {})
        checks.pop("leakage_clean", None)
        report["checks"] = checks
        report["passed"] = True
        row.sufficiency_report = report
        row.sufficiency_passed = True
        session.commit()

        with pytest.raises(ValueError, match="leakage"):
            orch.train(novabank_tenant, manifest.prediction_dataset_manifest_id, seed=42)
    engine.dispose()


def test_evaluate_does_not_auto_promote_even_if_gates_pass(projected_novabank, novabank_tenant):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        manifest = orch.build_dataset(novabank_tenant)
        model = orch.train(novabank_tenant, manifest.prediction_dataset_manifest_id, seed=42)
        evaluation = orch.evaluate(
            novabank_tenant,
            model.prediction_model_id,
            mark_validated_if_passing=False,
        )
        uow.commit()
        refreshed = orch.registry.get(novabank_tenant, model.prediction_model_id)
        assert refreshed is not None
        assert refreshed.model_state == ModelState.CANDIDATE
        assert evaluation.passed_validation_gates in (True, False)
    engine.dispose()
