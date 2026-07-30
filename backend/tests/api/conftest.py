"""Shared fixtures for the versioned API suite.

Under Phase 3 Prompt 7 the ``/api/v2`` and legacy root routes are RBAC-gated and
therefore resolve an authenticated :class:`SecurityContext` on every request.
Context resolution opens a database session (to set the transaction-local RLS
tenant and read principal rows in production). The deterministic compute itself
still uses the in-memory ``MockCatalogRepository``, so a migrated+seeded SQLite
database only satisfies the security pipeline — it does not change any Prompt 1-6
behaviour or expected outputs.
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
def _api_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Create, migrate and seed one SQLite database for the whole module."""
    db_path = tmp_path_factory.mktemp("apidb") / "test.db"
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
def _use_api_db(_api_db_url: str) -> Generator[None, None, None]:
    """Point the app at the module database for each test (post ``isolate_settings``)."""
    os.environ["DATABASE_URL"] = _api_db_url
    get_settings.cache_clear()
    reset_engine()
    init_engine(_api_db_url)
    yield
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)
