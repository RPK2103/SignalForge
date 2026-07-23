"""Persistence API dependency injection."""

from collections.abc import Generator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session_factory, init_engine
from app.db.unit_of_work import UnitOfWork
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.exceptions import DatabaseUnavailableError, PersistenceError
from app.services.persistence.leadership_brief_persistence_service import (
    LeadershipBriefPersistenceService,
)
from app.services.persistence.review_persistence_service import HumanReviewPersistenceService
from app.services.persistence.simulation_persistence_service import SimulationPersistenceService


def _ensure_database_configured() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise DatabaseUnavailableError("Database is not configured")


def get_db_session() -> Generator[Session, None, None]:
    _ensure_database_configured()
    init_engine()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_unit_of_work(session: Session = Depends(get_db_session)) -> UnitOfWork:
    return UnitOfWork(session)


def get_assessment_persistence_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> AssessmentPersistenceService:
    return AssessmentPersistenceService(uow)


def get_simulation_persistence_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> SimulationPersistenceService:
    return SimulationPersistenceService(uow)


def get_review_persistence_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> HumanReviewPersistenceService:
    return HumanReviewPersistenceService(uow)


def get_leadership_brief_persistence_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> LeadershipBriefPersistenceService:
    return LeadershipBriefPersistenceService(uow)


def map_persistence_exception(exc: PersistenceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)
