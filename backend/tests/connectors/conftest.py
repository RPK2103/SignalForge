"""Fixtures for connector ingestion tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import TenantContext


def _run_alembic(url: str, revision: str) -> None:
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    command.upgrade(Config("alembic.ini"), revision)


@pytest.fixture
def temp_database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'connectors.db').as_posix()}"


@pytest.fixture
def migrated_db(temp_database_url: str) -> Generator[str, None, None]:
    _run_alembic(temp_database_url, "head")
    yield temp_database_url
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
def tenant_a() -> TenantContext:
    return TenantContext.require("tenant-a")


@pytest.fixture
def tenant_b() -> TenantContext:
    return TenantContext.require("tenant-b")
