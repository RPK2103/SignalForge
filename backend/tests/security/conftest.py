"""Fixtures for the security test suite (Phase 3 Prompt 7)."""

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
from app.security.jwks import BoundedJwksCache
from app.security.jwt_verifier import EntraJwtVerifier
from tests.security.keys import FakeJwksClient, generate_rsa_keypair, public_jwk

ENTRA_ISSUER = "https://login.microsoftonline.com/entra-tenant-guid/v2.0"
ENTRA_AUDIENCE = "api://signalforge"
ENTRA_TENANT = "entra-tenant-guid"
ENTRA_JWKS_URI = "https://example.invalid/keys"
KID = "test-key-1"


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
    url = f"sqlite:///{(tmp_path / 'security.db').as_posix()}"
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
def client(migrated_db: str) -> Generator[TestClient, None, None]:
    os.environ["DATABASE_URL"] = migrated_db
    get_settings.cache_clear()
    reset_engine()
    init_engine(migrated_db)
    # No default Authorization header: security tests attach tokens explicitly.
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def rsa_key():
    return generate_rsa_keypair()


@pytest.fixture
def entra_verifier(rsa_key) -> EntraJwtVerifier:
    fake_client = FakeJwksClient([public_jwk(rsa_key, KID)])
    cache = BoundedJwksCache(fake_client, ttl_seconds=600)
    return EntraJwtVerifier(
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        allowed_tenant_ids=(ENTRA_TENANT,),
        allowed_algorithms=("RS256", "RS384", "RS512"),
        jwks_uri=ENTRA_JWKS_URI,
        jwks_cache=cache,
        clock_skew_seconds=60,
        max_token_bytes=8192,
    )


@pytest.fixture
def entra_verifier_with_client(rsa_key):
    """Return (verifier, fake_client) so tests can mutate JWKS behaviour."""
    fake_client = FakeJwksClient([public_jwk(rsa_key, KID)])
    cache = BoundedJwksCache(fake_client, ttl_seconds=600)
    verifier = EntraJwtVerifier(
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        allowed_tenant_ids=(ENTRA_TENANT,),
        allowed_algorithms=("RS256", "RS384", "RS512"),
        jwks_uri=ENTRA_JWKS_URI,
        jwks_cache=cache,
        clock_skew_seconds=60,
        max_token_bytes=8192,
    )
    return verifier, fake_client
