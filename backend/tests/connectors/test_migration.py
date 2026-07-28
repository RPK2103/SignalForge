"""Connector migration tests — upgrade from populated Prompt 1, downgrade, re-upgrade."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.db.session import reset_engine

P3_PROMPT1 = "p3_enterprise_foundation"
P3_PROMPT2 = "p3_connector_ingestion_foundation"


def _alembic_config():
    from alembic.config import Config

    return Config("alembic.ini")


def _upgrade(url: str, revision: str) -> None:
    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    command.upgrade(_alembic_config(), revision)


def _downgrade(url: str, revision: str) -> None:
    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    command.downgrade(_alembic_config(), revision)


@pytest.fixture
def temp_url(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'conn_mig.db').as_posix()}"
    yield url
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


def test_exactly_one_head_is_prompt2():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert heads == [P3_PROMPT2]


def test_upgrade_from_populated_prompt1_preserves_data(temp_url: str):
    _upgrade(temp_url, P3_PROMPT1)
    engine = create_engine(temp_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ent_data_sources "
                "(data_source_id, source_type, display_name, status, permission_classification, "
                "tenant_id, created_at, updated_at) "
                "VALUES ('ds_keep', 'github', 'Keep Me', 'registered', 'internal', "
                "'tenant-a', '2026-01-01', '2026-01-01')"
            )
        )
    engine.dispose()

    _upgrade(temp_url, "head")
    engine = create_engine(temp_url)
    tables = inspect(engine).get_table_names()
    assert "ent_connector_checkpoints" in tables
    assert "ent_ingestion_receipts" in tables
    assert "ent_ingestion_dead_letters" in tables
    assert "ent_pull_requests" in tables
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_name, freshness_state FROM ent_data_sources "
                "WHERE data_source_id='ds_keep'"
            )
        ).one()
        assert row[0] == "Keep Me"
        assert row[1] == "never_synced"
        cols = {c["name"] for c in inspect(engine).get_columns("ent_ingestion_runs")}
        assert "records_dead_lettered" in cols
        assert "request_count" in cols
    engine.dispose()

    _downgrade(temp_url, P3_PROMPT1)
    engine = create_engine(temp_url)
    tables = inspect(engine).get_table_names()
    assert "ent_connector_checkpoints" not in tables
    with engine.connect() as conn:
        name = conn.execute(
            text("SELECT display_name FROM ent_data_sources WHERE data_source_id='ds_keep'")
        ).scalar()
        assert name == "Keep Me"
    engine.dispose()

    _upgrade(temp_url, "head")
    engine = create_engine(temp_url)
    assert "ent_pull_requests" in inspect(engine).get_table_names()
    engine.dispose()
