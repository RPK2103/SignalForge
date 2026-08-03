"""Fixtures for PostgreSQL RLS tests of Prompt 8 tables.

Deferred locally when ``POSTGRES_TEST_URL`` is unset; mandatory in CI. Mirrors
tests/security_postgres to run every statement as the NON-superuser app role.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine, text

APP_URL = os.environ.get("POSTGRES_TEST_URL")
MIGRATION_URL = os.environ.get("POSTGRES_MIGRATION_URL", APP_URL or "")

pytestmark = pytest.mark.skipif(
    not APP_URL,
    reason=(
        "POSTGRES_TEST_URL not set: Prompt 8 PostgreSQL RLS tests are deferred "
        "locally. They are mandatory in CI."
    ),
)

_PROMPT8_TABLES = (
    "ent_observability_metric_rollups",
    "ent_slo_definitions",
    "ent_slo_evaluations",
    "ent_alert_events",
    "ent_ai_evaluation_results",
    "ent_ai_evaluation_runs",
    "ent_ai_evaluation_cases",
    "ent_ai_evaluation_datasets",
    "ent_prediction_quality_snapshots",
)


def _run_migrations(url: str) -> None:
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings
    from app.db.session import init_engine, reset_engine

    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    command.upgrade(Config("alembic.ini"), "head")
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _migrated() -> None:
    if not APP_URL:
        return
    _run_migrations(MIGRATION_URL)


@pytest.fixture
def app_engine() -> Generator[Engine, None, None]:
    if not APP_URL:
        pytest.skip("POSTGRES_TEST_URL not set")
    engine = create_engine(APP_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean(app_engine: Engine) -> Generator[None, None, None]:
    yield
    if not APP_URL:
        return
    priv = create_engine(MIGRATION_URL, future=True)
    with priv.begin() as conn:
        for table in _PROMPT8_TABLES:
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
    priv.dispose()


def assert_non_superuser(engine: Engine) -> None:
    with engine.connect() as conn:
        is_super = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    assert is_super is False, "Application role must not be a PostgreSQL superuser"
