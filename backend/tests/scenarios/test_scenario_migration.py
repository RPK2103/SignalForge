"""Migration tests for Continuous Scenario Intelligence."""

from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings
from app.db.session import reset_engine


def _cfg(url: str) -> Config:
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    return Config("alembic.ini")


def test_scenario_migration_upgrade_downgrade(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'scen_mig.db').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, "p3_delivery_prediction")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "ent_scenario_definitions",
        "ent_scenario_versions",
        "ent_scenario_watches",
        "ent_scenario_trigger_events",
        "ent_scenario_runs",
        "ent_scenario_feature_overlays",
        "ent_scenario_results",
        "ent_scenario_impacts",
        "ent_delivery_outcomes",
        "ent_prediction_feature_snapshots",
        "ent_delivery_graph_nodes",
    }
    assert expected.issubset(tables)

    command.downgrade(cfg, "p3_delivery_prediction")
    tables_after = set(inspect(create_engine(url)).get_table_names())
    assert "ent_scenario_definitions" not in tables_after
    assert "ent_delivery_outcomes" in tables_after

    command.upgrade(cfg, "head")
    command.check(cfg)
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


def test_single_alembic_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = script.get_heads()
    assert heads == ["p3_ai_chief_of_staff"]
