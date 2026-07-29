"""Tenant isolation tests for delivery prediction."""

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS
from app.services.prediction.orchestration import PredictionOrchestrationService

TENANT = {"X-SignalForge-Tenant-ID": "novabank"}
FOREIGN = {"X-SignalForge-Tenant-ID": "tenant-a"}


def test_tenant_a_cannot_see_novabank_outcomes_models_predictions(
    projected_novabank, novabank_tenant, tenant_a
):
    engine = get_engine(projected_novabank)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)

        nb_outcomes = uow.delivery_outcomes.list_for_horizon(
            novabank_tenant, horizon_days=DEFAULT_HORIZON_DAYS, limit=50
        )
        assert len(nb_outcomes) > 0

        a_outcomes = uow.delivery_outcomes.list_for_horizon(
            tenant_a, horizon_days=DEFAULT_HORIZON_DAYS, limit=50
        )
        assert len(a_outcomes) == 0

        manifest = orch.build_dataset(novabank_tenant)
        model = orch.train(novabank_tenant, manifest.prediction_dataset_manifest_id, seed=42)
        uow.commit()

        assert orch.registry.get(tenant_a, model.prediction_model_id) is None
        assert (
            uow.prediction_datasets.get(tenant_a, manifest.prediction_dataset_manifest_id) is None
        )
        assert len(orch.list_models(tenant_a)) == 0

        sample_outcome_id = nb_outcomes[0].delivery_outcome_id
        assert uow.delivery_outcomes.get(tenant_a, sample_outcome_id) is None
    engine.dispose()


def test_api_404_nondisclosure_wrong_tenant(client):
    project_id = build_entity_id("proj", "novabank", "rt-payments-rail")

    ok = client.get(f"/api/v3/predictions/projects/{project_id}", headers=TENANT)
    assert ok.status_code == 200

    foreign = client.get(
        f"/api/v3/predictions/projects/{project_id}",
        headers=FOREIGN,
    )
    assert foreign.status_code == 404
    body = foreign.json()
    # Non-disclosure: no novabank identifiers leaked in error detail.
    detail = str(body.get("detail", body)).lower()
    assert "novabank" not in detail or "not found" in detail

    outcomes_nb = client.get("/api/v3/predictions/outcomes", headers=TENANT)
    assert outcomes_nb.status_code == 200
    assert outcomes_nb.json()["total"] > 0

    outcomes_a = client.get("/api/v3/predictions/outcomes", headers=FOREIGN)
    assert outcomes_a.status_code == 200
    assert outcomes_a.json()["total"] == 0

    models_nb = client.get("/api/v3/predictions/models", headers=TENANT)
    assert models_nb.status_code == 200
    # May be empty before training; tenancy still scoped.
    models_a = client.get("/api/v3/predictions/models", headers=FOREIGN)
    assert models_a.status_code == 200
    assert models_a.json()["total"] == 0
