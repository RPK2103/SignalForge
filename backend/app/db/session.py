"""Database engine and session factory — no connections at import time."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

# Bounded, production-safe PostgreSQL pool/statement defaults (Prompt 7). These
# are validated envelopes, not incompatible SQLite options.
_PG_POOL_SIZE = 5
_PG_MAX_OVERFLOW = 10
_PG_POOL_TIMEOUT_SECONDS = 30
_PG_POOL_RECYCLE_SECONDS = 1800
_PG_CONNECT_TIMEOUT_SECONDS = 10
_PG_STATEMENT_TIMEOUT_MS = 30_000
_PG_APPLICATION_NAME = "signalforge-api"


def normalize_database_url(database_url: str) -> str:
    url = database_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _configure_sqlite_engine(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _configure_postgres_engine(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine, "connect")
    def _set_statement_timeout(dbapi_connection, _connection_record) -> None:
        # Bound every statement so a pathological query cannot exhaust a pooled
        # connection. Applied per physical connection at checkout time.
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f"SET statement_timeout = {_PG_STATEMENT_TIMEOUT_MS}")


def get_engine(database_url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    settings = get_settings()
    url = normalize_database_url(
        database_url or settings.database_url or "sqlite:///./signalforge.db"
    )
    connect_args: dict = {}
    engine_kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        # PostgreSQL (and other server databases): apply bounded pool settings.
        connect_args["connect_timeout"] = _PG_CONNECT_TIMEOUT_SECONDS
        connect_args["application_name"] = _PG_APPLICATION_NAME
        engine_kwargs.update(
            pool_size=_PG_POOL_SIZE,
            max_overflow=_PG_MAX_OVERFLOW,
            pool_timeout=_PG_POOL_TIMEOUT_SECONDS,
            pool_recycle=_PG_POOL_RECYCLE_SECONDS,
            pool_pre_ping=True,
        )
    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
    _configure_sqlite_engine(engine)
    _configure_postgres_engine(engine)
    return engine


def init_engine(database_url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    _engine = get_engine(database_url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope(database_url: str | None = None):
    if database_url is not None:
        engine = get_engine(database_url)
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            engine.dispose()
    else:
        session = get_session_factory()()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
