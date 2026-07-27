"""Seed idempotency tests."""

from sqlalchemy.orm import Session

from app.db.seed import seed_database
from app.db.session import get_engine, init_engine, reset_engine


def test_seed_idempotent(migrated_db: str):
    reset_engine()
    init_engine(migrated_db)
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        first = seed_database(session)
        session.commit()
        second = seed_database(session)
        session.commit()
        assert first["capabilities_created"] >= 1
        assert second["capabilities_created"] == 0
        assert second["engineers_created"] == 0
        assert second["scenarios_created"] == 0
    engine.dispose()
    reset_engine()
