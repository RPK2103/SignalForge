"""Fixtures for PostgreSQL RLS integration tests (Phase 3 Prompt 7).

Environment variables:
- ``POSTGRES_TEST_URL``    : connection URL for the NON-superuser application
                            role. Required; the suite is deferred locally when
                            unset and mandatory in CI (always set there).
- ``POSTGRES_MIGRATION_URL``: optional privileged URL used to run migrations and
                            grant the application role. Defaults to
                            ``POSTGRES_TEST_URL``.
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
        "POSTGRES_TEST_URL not set: PostgreSQL RLS tests are deferred locally. "
        "They are mandatory in CI (the workflow always provides POSTGRES_TEST_URL)."
    ),
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
    """Best-effort cleanup of security tables between tests (owner/privileged)."""
    yield
    if not APP_URL:
        return
    priv = create_engine(MIGRATION_URL, future=True)
    with priv.begin() as conn:
        # Disable RLS enforcement for cleanup by using the privileged/owner role;
        # deletes still require a tenant context under FORCE RLS, so set a wildcard
        # bypass by temporarily setting the GUC per known tenant is unnecessary here
        # because the privileged migration role can TRUNCATE.
        for table in (
            "ent_role_assignments",
            "ent_security_audit_events",
            "ent_security_principals",
            "ent_identity_providers",
        ):
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
    priv.dispose()


def assert_non_superuser(engine: Engine) -> None:
    with engine.connect() as conn:
        is_super = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    assert is_super is False, "Application role must not be a PostgreSQL superuser"
