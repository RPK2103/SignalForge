"""Shared fixtures for Prompt 9 NovaBank demo tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine, init_engine, reset_engine
from app.demo.novabank.constants import TENANT_ID
from app.demo.novabank.service import NovaBankDemoService
from app.security.context import internal_system_context
from app.security.enums import SecurityRole
from app.security.permissions import permissions_for_roles


def _run_alembic(url: str) -> None:
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def demo_db_url(tmp_path: Path) -> Generator[str, None, None]:
    url = f"sqlite:///{(tmp_path / 'demo.db').as_posix()}"
    _run_alembic(url)
    yield url
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def demo_session(demo_db_url: str) -> Generator[Session, None, None]:
    reset_engine()
    init_engine(demo_db_url)
    engine = get_engine(demo_db_url)
    session = Session(engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()
        reset_engine()


@pytest.fixture
def demo_security():
    return internal_system_context(
        TENANT_ID,
        correlation_id="test-demo-seed",
        roles=frozenset({SecurityRole.TENANT_ADMIN}),
        permissions=permissions_for_roles(frozenset({SecurityRole.TENANT_ADMIN})),
    )


@pytest.fixture
def reader_security():
    return internal_system_context(
        TENANT_ID,
        correlation_id="test-demo-reader",
        roles=frozenset({SecurityRole.EXECUTIVE_READER}),
        permissions=permissions_for_roles(frozenset({SecurityRole.EXECUTIVE_READER})),
    )


@pytest.fixture
def seeded_demo(demo_session: Session, demo_security) -> dict:
    service = NovaBankDemoService(demo_session, demo_security)
    return service.seed()
