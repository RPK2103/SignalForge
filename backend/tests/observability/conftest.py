"""Fixtures for the observability test suite (Phase 3 Prompt 8).

Installs a deterministic in-memory telemetry provider AFTER application startup
(the lifespan would otherwise select a provider from settings) so tests can assert
exact metric values with zero network calls.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.main import app
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import (
    reset_observability_provider,
    set_observability_provider,
)


def _run_alembic(url: str, revision: str) -> None:
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    command.upgrade(Config("alembic.ini"), revision)


@pytest.fixture
def migrated_db(tmp_path: Path) -> Generator[str, None, None]:
    url = f"sqlite:///{(tmp_path / 'observability.db').as_posix()}"
    _run_alembic(url, "head")
    yield url
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def db_session(migrated_db: str) -> Generator[Session, None, None]:
    reset_engine()
    init_engine(migrated_db)
    engine = get_engine(migrated_db)
    session = Session(engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()
        reset_engine()


@pytest.fixture
def uow(db_session: Session) -> UnitOfWork:
    return UnitOfWork(db_session)


@pytest.fixture
def provider() -> InMemoryObservabilityProvider:
    return InMemoryObservabilityProvider()


@pytest.fixture
def obs_client(
    migrated_db: str, provider: InMemoryObservabilityProvider
) -> Generator[tuple[TestClient, InMemoryObservabilityProvider], None, None]:
    os.environ["DATABASE_URL"] = migrated_db
    get_settings.cache_clear()
    reset_engine()
    init_engine(migrated_db)
    with TestClient(app) as test_client:
        # Override whatever the lifespan installed with the deterministic provider.
        set_observability_provider(provider)
        yield test_client, provider
    reset_observability_provider()
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)
