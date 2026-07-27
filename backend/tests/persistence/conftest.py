"""Shared persistence test fixtures."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.seed import seed_database
from app.db.session import get_engine, init_engine, reset_engine
from app.db.unit_of_work import UnitOfWork
from app.main import app
from app.repositories.mock_catalog_repository import MockCatalogRepository


@pytest.fixture
def temp_database_url(tmp_path: Path) -> str:
    db_path = tmp_path / "test.db"
    return f"sqlite:///{db_path.as_posix()}"


@pytest.fixture
def migrated_db(temp_database_url: str) -> Generator[str, None, None]:
    os.environ["DATABASE_URL"] = temp_database_url
    get_settings.cache_clear()
    reset_engine()
    init_engine(temp_database_url)
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield temp_database_url
    reset_engine()
    get_settings.cache_clear()
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]


@pytest.fixture
def seeded_db(migrated_db: str) -> Generator[str, None, None]:
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        seed_database(session)
        session.commit()
    engine.dispose()
    yield migrated_db


@pytest.fixture
def db_session(seeded_db: str) -> Generator[Session, None, None]:
    reset_engine()
    init_engine(seeded_db)
    engine = get_engine(seeded_db)
    session = Session(engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()
        reset_engine()


@pytest.fixture
def unit_of_work(db_session: Session) -> UnitOfWork:
    return UnitOfWork(db_session)


@pytest.fixture
def mock_catalog() -> MockCatalogRepository:
    return MockCatalogRepository()


@pytest.fixture
def persistence_client(seeded_db: str) -> Generator[TestClient, None, None]:
    os.environ["DATABASE_URL"] = seeded_db
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as client:
        yield client
    reset_engine()
    get_settings.cache_clear()
