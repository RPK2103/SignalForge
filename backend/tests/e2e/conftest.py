"""Shared fixtures for the end-to-end flow suite.

The catalog-driven readiness/simulation flows use module-level ``TestClient``
instances. Under Phase 3 Prompt 7 those ``/api/v2`` routes are RBAC-gated and
resolve an authenticated :class:`SecurityContext` (which opens a DB session) on
every request. A migrated+seeded SQLite database only satisfies that security
pipeline; the deterministic compute still uses the in-memory catalog, so no
Prompt 1-6 behaviour changes. Flows that already request ``persistence_client``
manage their own database and are unaffected by the autouse fixture below.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.seed import seed_database
from app.db.session import get_engine, init_engine, reset_engine


@pytest.fixture(scope="module")
def _e2e_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    db_path = tmp_path_factory.mktemp("e2edb") / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")

    engine = get_engine(url)
    with Session(engine) as session:
        seed_database(session)
        session.commit()
    engine.dispose()
    return url


@pytest.fixture(autouse=True)
def _use_e2e_db(request: pytest.FixtureRequest, _e2e_db_url: str) -> Generator[None, None, None]:
    # Flows that manage their own database via ``persistence_client`` must not be
    # overridden by the module database.
    if "persistence_client" in request.fixturenames:
        yield
        return
    os.environ["DATABASE_URL"] = _e2e_db_url
    get_settings.cache_clear()
    reset_engine()
    init_engine(_e2e_db_url)
    yield
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)
