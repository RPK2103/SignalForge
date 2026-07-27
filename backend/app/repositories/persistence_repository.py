"""Repository interfaces for persisted aggregates."""

from typing import Protocol
from uuid import UUID

from app.domain.enums import HumanReviewState
from app.domain.leadership_brief_models import LeadershipBriefRecord
from app.domain.persistence_models import (
    AssessmentRecord,
    AuditEventRecord,
    HumanReviewRecord,
    PaginatedAssessmentList,
    PaginatedSimulationList,
    SimulationRecord,
)


class AssessmentRepository(Protocol):
    def add(self, record: AssessmentRecord) -> None: ...

    def add_risk_projections(self, record_id: UUID, findings: list[dict]) -> None: ...

    def add_trace_projections(self, record_id: UUID, traces: list[dict]) -> None: ...

    def get_by_record_id(self, record_id: UUID) -> AssessmentRecord: ...

    def list(
        self,
        *,
        project_id: str | None = None,
        assessment_id: str | None = None,
        review_state: HumanReviewState | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedAssessmentList: ...

    def list_by_deterministic_id(self, assessment_id: str) -> list[AssessmentRecord]: ...


class SimulationRepository(Protocol):
    def add(self, record: SimulationRecord) -> None: ...

    def get_by_record_id(self, record_id: UUID) -> SimulationRecord: ...

    def list(
        self,
        *,
        project_id: str | None = None,
        simulation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedSimulationList: ...

    def list_by_deterministic_id(self, simulation_id: str) -> list[SimulationRecord]: ...


class HumanReviewRepository(Protocol):
    def add(self, review: HumanReviewRecord) -> None: ...

    def list_for_assessment(self, record_id: UUID) -> list[HumanReviewRecord]: ...

    def get_latest_for_assessment(self, record_id: UUID) -> HumanReviewRecord | None: ...


class AuditEventRepository(Protocol):
    def append(self, event: AuditEventRecord) -> None: ...

    def list_for_aggregate(
        self,
        aggregate_type: str,
        aggregate_record_id: UUID,
    ) -> list[AuditEventRecord]: ...


class LeadershipBriefRepository(Protocol):
    def add(self, record: LeadershipBriefRecord) -> None: ...

    def get_by_record_id(self, record_id: UUID) -> LeadershipBriefRecord: ...

    def list_for_assessment(self, assessment_record_id: UUID) -> list[LeadershipBriefRecord]: ...
