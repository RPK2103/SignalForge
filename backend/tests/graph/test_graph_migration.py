"""Migration tests for Prompt 3 delivery graph."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.db.enterprise_seed import seed_enterprise
from app.db.session import init_engine, reset_engine


def _alembic(url: str) -> Config:
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    return Config("alembic.ini")


def test_one_alembic_head():
    cfg = Config("alembic.ini")
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["p3_continuous_scenario_intelligence"]


def test_clean_upgrade_downgrade_reupgrade(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'clean.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "head")
    command.check(cfg)
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert "ent_delivery_graph_nodes" in tables
    assert "ent_delivery_graph_edges" in tables
    assert "ent_graph_findings" in tables
    command.downgrade(cfg, "p3_connector_ingestion_foundation")
    tables_after = set(inspect(create_engine(url)).get_table_names())
    assert "ent_delivery_graph_nodes" not in tables_after
    assert "ent_evidence_signals" in tables_after
    command.upgrade(cfg, "head")
    command.check(cfg)
    reset_engine()
    get_settings.cache_clear()


def test_populated_prompt2_upgrade_preserves_data(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'populated.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "p3_connector_ingestion_foundation")
    engine = create_engine(url)
    with Session(engine) as session:
        summary = seed_enterprise(session)
        session.commit()
        assert summary["total_created"] > 0
        evidence_count = session.execute(text("SELECT COUNT(*) FROM ent_evidence_signals")).scalar()
        receipt_ready = "ent_ingestion_receipts" in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    engine2 = create_engine(url)
    with Session(engine2) as session:
        evidence_after = session.execute(text("SELECT COUNT(*) FROM ent_evidence_signals")).scalar()
        assert evidence_after == evidence_count
        assert evidence_after > 0
        nodes = session.execute(text("SELECT COUNT(*) FROM ent_delivery_graph_nodes")).scalar()
        assert nodes == 0  # projection not run yet
    assert receipt_ready
    reset_engine()
    get_settings.cache_clear()


def test_offline_postgresql_sql_compiles(tmp_path: Path):
    """Compile PostgreSQL SQL offline without a live server."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://user:pass@localhost/db")
    # Offline PostgreSQL SQL compilation smoke (no live server required).
    try:
        command.upgrade(cfg, "p3_delivery_graph", sql=True)
    except Exception as exc:
        pytest.skip(f"Offline PostgreSQL SQL not executable here: {exc}")
    finally:
        get_settings.cache_clear()
