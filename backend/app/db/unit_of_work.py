"""Unit of Work for atomic persistence transactions."""

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from app.db.repositories.sql_repositories import (
    SqlAssessmentRepository,
    SqlAuditEventRepository,
    SqlCatalogRepository,
    SqlHumanReviewRepository,
    SqlSimulationRepository,
)
from app.repositories.catalog_repository import CatalogRepository

T = TypeVar("T")


class UnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog: CatalogRepository = SqlCatalogRepository(session)
        self.assessments = SqlAssessmentRepository(session)
        self.simulations = SqlSimulationRepository(session)
        self.reviews = SqlHumanReviewRepository(session)
        self.audit_events = SqlAuditEventRepository(session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def execute(self, callback: Callable[["UnitOfWork"], T]) -> T:
        try:
            result = callback(self)
            self.commit()
            return result
        except Exception:
            self.rollback()
            raise
