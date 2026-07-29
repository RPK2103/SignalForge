"""Cross-database reproducibility tests for delivery prediction."""

from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.db.enterprise_seed import TENANT_ID, seed_enterprise
from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import TenantContext
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.projection_service import GraphProjectionService
from app.services.prediction.orchestration import PredictionOrchestrationService


def _prepare_db(path: Path) -> str:
    url = f"sqlite:///{path.as_posix()}"
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    command.upgrade(Config("alembic.ini"), "head")

    tenant = TenantContext.require(TENANT_ID)
    engine = get_engine(url)
    with Session(engine) as session:
        seed_enterprise(session)
        session.commit()
    with Session(engine) as session:
        uow = UnitOfWork(session)
        GraphProjectionService(uow).full_rebuild(tenant)
        GraphAnalysisService(uow).analyze(tenant)
        uow.commit()
    engine.dispose()
    return url


def _train_pipeline(url: str) -> dict:
    tenant = TenantContext.require(TENANT_ID)
    reset_engine()
    init_engine(url)
    engine = get_engine(url)
    with Session(engine) as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        manifest = orch.build_dataset(tenant)
        model = orch.train(tenant, manifest.prediction_dataset_manifest_id, seed=42)
        evaluation = orch.evaluate(tenant, model.prediction_model_id)
        uow.commit()
        result = {
            "dataset_hash": manifest.dataset_hash,
            "parameter_hash": model.parameter_hash,
            "train_row_ids_hash": manifest.train_row_ids_hash,
            "calibration_row_ids_hash": manifest.calibration_row_ids_hash,
            "test_row_ids_hash": manifest.test_row_ids_hash,
            "brier_score": evaluation.brier_score,
            "log_loss": evaluation.log_loss,
            "expected_calibration_error": evaluation.expected_calibration_error,
            "baseline_brier_score": evaluation.baseline_brier_score,
            "row_count": evaluation.row_count,
        }
    engine.dispose()
    return result


def test_two_temp_dbs_reproducible(tmp_path: Path):
    url_a = _prepare_db(tmp_path / "repro_a.db")
    result_a = _train_pipeline(url_a)

    url_b = _prepare_db(tmp_path / "repro_b.db")
    result_b = _train_pipeline(url_b)

    assert result_a["dataset_hash"] == result_b["dataset_hash"]
    assert result_a["parameter_hash"] == result_b["parameter_hash"]
    assert result_a["train_row_ids_hash"] == result_b["train_row_ids_hash"]
    assert result_a["calibration_row_ids_hash"] == result_b["calibration_row_ids_hash"]
    assert result_a["test_row_ids_hash"] == result_b["test_row_ids_hash"]
    assert result_a["row_count"] == result_b["row_count"]

    # Metrics within tight absolute tolerance (float path determinism).
    for key in (
        "brier_score",
        "log_loss",
        "expected_calibration_error",
        "baseline_brier_score",
    ):
        assert abs(result_a[key] - result_b[key]) < 1e-9

    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)
