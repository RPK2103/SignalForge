"""Prediction validation-run telemetry integration (Prompt 8 completeness).

Drives ``PredictionOrchestrator.evaluate`` — the reachable validation-gate
boundary used by the prediction CLI — and asserts one terminal
``prediction.validation_runs`` sample after durable commit.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS
from app.domain.prediction_enums import ModelState
from app.observability.attributes import ALLOWED_ATTRIBUTES, TelemetryAttributePolicy
from app.observability.metrics import MetricName
from app.observability.metrics_reader import MetricsReader
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import (
    get_observability_provider,
    reset_observability_provider,
    set_observability_provider,
)
from app.security.context import internal_system_context
from app.security.enums import Permission, SecurityRole
from app.security.exceptions import AuthorizationError
from app.services.prediction.orchestration import PredictionOrchestrationService


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _validator_ctx(tenant: str = "novabank"):
    return internal_system_context(
        tenant,
        correlation_id="pred-val",
        roles=frozenset({SecurityRole.TENANT_ADMIN}),
    )


def _denied_ctx(tenant: str = "novabank"):
    return internal_system_context(
        tenant,
        correlation_id="pred-val-denied",
        roles=frozenset({SecurityRole.EXECUTIVE_READER}),
        permissions=frozenset({Permission.PREDICTIONS_READ}),
    )


def _train_candidate(uow, tenant):
    orch = PredictionOrchestrationService(uow)
    manifest = orch.build_dataset(tenant, horizon_days=DEFAULT_HORIZON_DAYS)
    uow.commit()
    model = orch.train(tenant, manifest.prediction_dataset_manifest_id, seed=42)
    uow.commit()
    return orch, model


def test_validation_run_emits_terminal_outcome_after_commit(
    projected_novabank, novabank_tenant, obs_provider
):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        evaluation = orch.evaluate(
            novabank_tenant,
            model.prediction_model_id,
            security=_validator_ctx(),
        )
        # Pending until commit.
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0
        uow.commit()
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 1
        # Exactly one terminal outcome for the run.
        outcomes = {
            dict(attrs).get("outcome")
            for (name, attrs), _ in obs_provider.counters.items()
            if name == MetricName.PREDICTION_VALIDATION_RUNS
        }
        assert len(outcomes) == 1
        assert outcomes.pop() in {"passed", "failed", "insufficient_data"}
        assert evaluation.prediction_model_id == model.prediction_model_id


def test_validation_rollback_discards_success(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        orch.evaluate(novabank_tenant, model.prediction_model_id, security=_validator_ctx())
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0
        uow.rollback()
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0


def test_validation_commit_failure_discards_success(
    projected_novabank, novabank_tenant, obs_provider, monkeypatch
):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        orch.evaluate(novabank_tenant, model.prediction_model_id, security=_validator_ctx())

        def _boom():
            raise RuntimeError("validation commit failed")

        monkeypatch.setattr(uow.session, "commit", _boom)
        with pytest.raises(RuntimeError, match="validation commit failed"):
            uow.commit()
        uow.rollback()
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0


def test_validation_authorization_denial_not_counted(
    projected_novabank, novabank_tenant, obs_provider
):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        with pytest.raises(AuthorizationError):
            orch.evaluate(
                novabank_tenant,
                model.prediction_model_id,
                security=_denied_ctx(),
            )
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0


def test_validation_missing_security_fails_closed(
    projected_novabank, novabank_tenant, obs_provider
):
    """Direct call with security=None must deny — no optional bypass."""
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        with pytest.raises(AuthorizationError) as exc_info:
            orch.evaluate(
                novabank_tenant,
                model.prediction_model_id,
                security=None,  # type: ignore[arg-type]
            )
        assert exc_info.value.reason_code == "no_security_context"
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0


def test_validation_empty_roles_fails_closed(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        empty = internal_system_context(
            "novabank",
            correlation_id="pred-val-empty",
            roles=frozenset(),
            permissions=frozenset(),
        )
        with pytest.raises(AuthorizationError):
            orch.evaluate(
                novabank_tenant,
                model.prediction_model_id,
                security=empty,
            )
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0


def test_validation_wrong_tenant_not_counted(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        with pytest.raises(AuthorizationError):
            orch.evaluate(
                novabank_tenant,
                model.prediction_model_id,
                security=_validator_ctx("othercorp"),
            )
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 0


def test_validation_missing_model_emits_error(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        obs_provider.reset()
        with pytest.raises(LookupError):
            orch.evaluate(
                novabank_tenant,
                "model-does-not-exist",
                security=_validator_ctx(),
            )
        assert (
            obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS, outcome="error") == 1
        )


def test_rejected_model_outcome(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        model.model_state = ModelState.REJECTED
        uow.prediction_models.update(novabank_tenant, model)
        uow.commit()
        obs_provider.reset()
        orch.evaluate(
            novabank_tenant,
            model.prediction_model_id,
            security=_validator_ctx(),
        )
        uow.commit()
        assert (
            obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS, outcome="rejected")
            == 1
        )


def test_validation_telemetry_provider_failure_keeps_result(projected_novabank, novabank_tenant):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        set_observability_provider(ExplodingProvider())
        try:
            evaluation = orch.evaluate(
                novabank_tenant,
                model.prediction_model_id,
                security=_validator_ctx(),
            )
            uow.commit()
            assert evaluation is not None
        finally:
            reset_observability_provider()


def test_validation_attributes_are_bounded(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        orch.evaluate(
            novabank_tenant,
            model.prediction_model_id,
            security=_validator_ctx(),
        )
        uow.commit()
        for _name, attrs in obs_provider.counters:
            keys = set(dict(attrs))
            assert keys <= ALLOWED_ATTRIBUTES
            assert "tenant_id" not in keys
            assert "prediction_model_id" not in keys
            for value in dict(attrs).values():
                assert model.prediction_model_id not in value


def test_adversarial_validation_attribute_values_redacted():
    policy = TelemetryAttributePolicy()
    clean = policy.sanitize(
        {
            "model_version": "alice@example.com",
            "outcome": "passed",
            "evaluation_type": "550e8400-e29b-41d4-a716-446655440000",
        }
    )
    assert clean["model_version"] == "redacted"
    assert clean["evaluation_type"] == "redacted"
    assert clean["outcome"] == "passed"


def test_validation_metric_reaches_reader(projected_novabank, novabank_tenant, obs_provider):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        orch.evaluate(
            novabank_tenant,
            model.prediction_model_id,
            security=_validator_ctx(),
        )
        uow.commit()
        reader = MetricsReader(get_observability_provider())
        indicator = reader.prediction_validation_total()
        assert indicator.sample_count == 1
        assert indicator.value == 1.0


def test_replayed_validation_counts_separately(projected_novabank, novabank_tenant, obs_provider):
    """Each genuine evaluate call after the ID clock advances is a new run."""
    import time

    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch, model = _train_candidate(uow, novabank_tenant)
        obs_provider.reset()
        first = orch.evaluate(novabank_tenant, model.prediction_model_id, security=_validator_ctx())
        uow.commit()
        time.sleep(1.05)
        second = orch.evaluate(
            novabank_tenant, model.prediction_model_id, security=_validator_ctx()
        )
        uow.commit()
        assert first.prediction_model_evaluation_id != second.prediction_model_evaluation_id
        assert obs_provider.counter_total(MetricName.PREDICTION_VALIDATION_RUNS) == 2
