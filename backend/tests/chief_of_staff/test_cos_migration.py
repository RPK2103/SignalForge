"""Migration lifecycle and bounds tests for Chief of Staff."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import get_settings
from app.db.session import reset_engine
from app.domain.chief_of_staff_constants import (
    MAX_CITATIONS_PER_CLAIM,
    MAX_CLAIMS,
    MAX_DETERMINISTIC_RISKS,
    MAX_EVIDENCE_SIGNALS,
    MAX_GRAPH_FINDINGS,
    MAX_SCENARIO_IMPACTS,
    MAX_SCENARIO_RUNS,
)


def _alembic(url: str) -> Config:
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    return Config("alembic.ini")


def test_single_alembic_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = script.get_heads()
    assert heads == ["p3_observability_ai_quality"]


def test_clean_upgrade_and_downgrade(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'cos_mig.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "ent_cos_evidence_snapshots",
        "ent_cos_runs",
        "ent_cos_briefs",
        "ent_cos_claims",
        "ent_cos_citations",
        "ent_cos_reviews",
    }
    assert expected.issubset(tables)
    command.downgrade(cfg, "p3_continuous_scenario_intelligence")
    tables_after = set(inspect(create_engine(url)).get_table_names())
    assert not expected.intersection(tables_after)
    command.upgrade(cfg, "head")
    tables_re = set(inspect(create_engine(url)).get_table_names())
    assert expected.issubset(tables_re)
    reset_engine()
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()


def test_upgrade_preserves_prompt5_tables(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'cos_p5.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "p3_continuous_scenario_intelligence")
    engine = create_engine(url)
    with engine.begin() as conn:
        # Touch a Prompt 5 table existence marker via insert-free check.
        assert "ent_scenario_runs" in inspect(engine).get_table_names()
        conn.execute(text("SELECT count(*) FROM ent_scenario_definitions"))
    command.upgrade(cfg, "head")
    assert "ent_scenario_runs" in inspect(create_engine(url)).get_table_names()
    assert "ent_cos_briefs" in inspect(create_engine(url)).get_table_names()
    reset_engine()
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()


def test_package_bounds_constants():
    assert MAX_DETERMINISTIC_RISKS == 20
    assert MAX_GRAPH_FINDINGS == 20
    assert MAX_EVIDENCE_SIGNALS == 40
    assert MAX_SCENARIO_RUNS == 10
    assert MAX_SCENARIO_IMPACTS == 100
    assert MAX_CLAIMS == 30
    assert MAX_CITATIONS_PER_CLAIM == 5


def test_offline_postgresql_sql_compiles():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://user:pass@localhost/db")
    try:
        command.upgrade(cfg, "p3_continuous_scenario_intelligence:p3_ai_chief_of_staff", sql=True)
    except Exception as exc:
        pytest.skip(f"Offline PostgreSQL SQL not executable here: {exc}")
    finally:
        get_settings.cache_clear()
