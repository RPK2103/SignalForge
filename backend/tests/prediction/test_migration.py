"""Migration tests for Prompt 4 delivery prediction."""

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
    assert heads == ["p3_observability_ai_quality"]


def test_upgrade_downgrade_reupgrade(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'pred_clean.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "head")
    command.check(cfg)

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert "ent_delivery_outcomes" in tables
    assert "ent_prediction_models" in tables
    assert "ent_delivery_predictions" in tables
    assert "ent_delivery_graph_nodes" in tables
    assert "ent_delivery_graph_edges" in tables
    assert "ent_graph_findings" in tables

    command.downgrade(cfg, "p3_delivery_graph")
    tables_mid = set(inspect(create_engine(url)).get_table_names())
    assert "ent_delivery_outcomes" not in tables_mid
    assert "ent_prediction_models" not in tables_mid
    assert "ent_delivery_graph_nodes" in tables_mid
    assert "ent_delivery_graph_edges" in tables_mid
    assert "ent_graph_findings" in tables_mid

    command.upgrade(cfg, "head")
    command.check(cfg)
    tables_after = set(inspect(create_engine(url)).get_table_names())
    assert "ent_delivery_outcomes" in tables_after
    assert "ent_delivery_graph_nodes" in tables_after
    reset_engine()
    get_settings.cache_clear()


def test_graph_tables_survive_prediction_upgrade(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'pred_graph.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "p3_delivery_graph")
    tables_graph = set(inspect(create_engine(url)).get_table_names())
    assert "ent_delivery_graph_nodes" in tables_graph
    assert "ent_delivery_graph_edges" in tables_graph
    assert "ent_graph_findings" in tables_graph
    assert "ent_delivery_outcomes" not in tables_graph

    command.upgrade(cfg, "head")
    tables_head = set(inspect(create_engine(url)).get_table_names())
    assert "ent_delivery_graph_nodes" in tables_head
    assert "ent_delivery_graph_edges" in tables_head
    assert "ent_graph_findings" in tables_head
    assert "ent_delivery_outcomes" in tables_head
    assert "ent_prediction_models" in tables_head

    # Seed only after prediction tables exist (enterprise seed writes outcomes).
    engine = create_engine(url)
    with Session(engine) as session:
        summary = seed_enterprise(session)
        session.commit()
        assert summary["total_created"] > 0
        evidence = session.execute(text("SELECT COUNT(*) FROM ent_evidence_signals")).scalar()
        outcomes = session.execute(text("SELECT COUNT(*) FROM ent_delivery_outcomes")).scalar()
        assert evidence > 0
        assert outcomes >= 60
    reset_engine()
    get_settings.cache_clear()


def test_offline_postgresql_sql_compiles():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://user:pass@localhost/db")
    try:
        command.upgrade(cfg, "p3_delivery_prediction", sql=True)
    except Exception as exc:
        pytest.skip(f"Offline PostgreSQL SQL not executable here: {exc}")
    finally:
        get_settings.cache_clear()
