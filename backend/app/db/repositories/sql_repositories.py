"""SQLAlchemy repository implementations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.assessment import Assessment, AssessmentDecisionTrace, AssessmentRiskFinding
from app.db.models.audit import AuditEvent
from app.db.models.catalog import Capability, Engineer, EngineerCapability, Project, ProjectRequirement
from app.db.models.review import HumanReview
from app.db.models.simulation import Simulation
from app.domain.enums import EvidenceSource, HumanReviewState
from app.domain.models import (
    CapabilityDefinition,
    EngineerCapability as DomainEngineerCapability,
    EngineerProfile,
    ProjectProfile,
    ProjectRequirement as DomainProjectRequirement,
)
from app.domain.persistence_models import (
    AssessmentListItem,
    AssessmentRecord,
    AuditEventRecord,
    HumanReviewRecord,
    PaginatedAssessmentList,
    PaginatedSimulationList,
    SimulationListItem,
    SimulationRecord,
)
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.engineer import EngineerProfile as LegacyEngineerProfile
from app.schemas.project_fit import ProjectRequirements
from app.services.persistence.exceptions import RecordNotFoundError


def _to_assessment_record(row: Assessment) -> AssessmentRecord:
    return AssessmentRecord(
        assessment_record_id=row.assessment_record_id,
        assessment_id=row.assessment_id,
        project_id=row.project_id,
        policy_version=row.policy_version,
        schema_version=row.schema_version,
        input_snapshot=row.input_snapshot,
        input_snapshot_hash=row.input_snapshot_hash,
        result_snapshot=row.result_snapshot,
        result_snapshot_hash=row.result_snapshot_hash,
        readiness_score=row.readiness_score,
        confidence_score=row.confidence_score,
        confidence_level=row.confidence_level,
        created_at=row.created_at,
        actor_reference=row.actor_reference,
    )


def _to_simulation_record(row: Simulation) -> SimulationRecord:
    return SimulationRecord(
        simulation_record_id=row.simulation_record_id,
        simulation_id=row.simulation_id,
        project_id=row.project_id,
        operation_type=row.operation_type,
        policy_version=row.policy_version,
        schema_version=row.schema_version,
        input_snapshot=row.input_snapshot,
        input_snapshot_hash=row.input_snapshot_hash,
        baseline_snapshot=row.baseline_snapshot,
        baseline_snapshot_hash=row.baseline_snapshot_hash,
        proposed_snapshot=row.proposed_snapshot,
        proposed_snapshot_hash=row.proposed_snapshot_hash,
        result_snapshot=row.result_snapshot,
        result_snapshot_hash=row.result_snapshot_hash,
        readiness_delta=row.readiness_delta,
        confidence_delta=row.confidence_delta,
        created_at=row.created_at,
        actor_reference=row.actor_reference,
    )


class SqlCatalogRepository(CatalogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_engineer_names(self) -> list[str]:
        rows = self._session.scalars(select(Engineer.name).order_by(Engineer.name)).all()
        return list(rows)

    def get_legacy_engineer(self, name: str) -> LegacyEngineerProfile | None:
        normalized = name.strip().lower()
        row = self._session.scalar(
            select(Engineer).where(func.lower(Engineer.name) == normalized)
        )
        if row is None:
            return None
        return self._engineer_to_legacy(row)

    def list_legacy_engineers(self) -> list[LegacyEngineerProfile]:
        rows = self._session.scalars(select(Engineer).order_by(Engineer.name)).all()
        return [self._engineer_to_legacy(row) for row in rows]

    def get_legacy_project(self, name: str) -> ProjectRequirements | None:
        row = self._session.scalar(select(Project).where(Project.name == name.strip()))
        if row is None:
            return None
        return self._project_to_legacy(row)

    def resolve_engineer_name(self, name: str) -> str | None:
        normalized = name.strip().lower()
        row = self._session.scalar(
            select(Engineer).where(func.lower(Engineer.name) == normalized)
        )
        return row.name if row else None

    def get_domain_engineers(self) -> list[EngineerProfile]:
        rows = self._session.scalars(
            select(Engineer).order_by(Engineer.name)
        ).all()
        return [self._engineer_to_domain(row) for row in rows]

    def get_domain_engineer_by_id(self, engineer_id: str) -> EngineerProfile | None:
        row = self._session.get(Engineer, engineer_id.strip().lower())
        if row is None:
            return None
        return self._engineer_to_domain(row)

    def get_domain_project(self, name: str) -> ProjectProfile | None:
        row = self._session.scalar(select(Project).where(Project.name == name.strip()))
        if row is None:
            return None
        return self._project_to_domain(row)

    def get_domain_project_by_id(self, project_id: str) -> ProjectProfile | None:
        row = self._session.get(Project, project_id.strip().lower())
        if row is None:
            return None
        return self._project_to_domain(row)

    def list_domain_projects(self) -> list[ProjectProfile]:
        rows = self._session.scalars(select(Project).order_by(Project.name)).all()
        return [self._project_to_domain(row) for row in rows]

    def _engineer_to_domain(self, row: Engineer) -> EngineerProfile:
        caps = self._session.scalars(
            select(EngineerCapability).where(EngineerCapability.engineer_id == row.engineer_id)
        ).all()
        return EngineerProfile(
            id=row.engineer_id,
            name=row.name,
            experience_years=row.experience_years,
            capabilities=[
                DomainEngineerCapability(
                    capability_id=cap.capability_id,
                    proficiency=cap.proficiency,
                    evidence_sources=[
                        EvidenceSource(source) for source in (cap.evidence_sources or [])
                    ],
                )
                for cap in caps
            ],
            has_certifications=row.has_certifications,
            has_project_history=row.has_project_history,
        )

    def _engineer_to_legacy(self, row: Engineer) -> LegacyEngineerProfile:
        domain = self._engineer_to_domain(row)
        cap_rows = self._session.scalars(
            select(Capability).join(
                EngineerCapability,
                EngineerCapability.capability_id == Capability.capability_id,
            ).where(EngineerCapability.engineer_id == row.engineer_id)
        ).all()
        id_to_name = {cap.capability_id: cap.name for cap in cap_rows}
        skills = [id_to_name.get(c.capability_id, c.capability_id) for c in domain.capabilities]
        return LegacyEngineerProfile(
            name=row.name,
            experience=int(row.experience_years),
            skills=skills,
            certifications=["Certified"] if row.has_certifications else [],
            projects=["Demo Project"] if row.has_project_history else [],
        )

    def _project_to_domain(self, row: Project) -> ProjectProfile:
        reqs = self._session.scalars(
            select(ProjectRequirement).where(ProjectRequirement.project_id == row.project_id)
        ).all()
        return ProjectProfile(
            id=row.project_id,
            name=row.name,
            requirements=[
                DomainProjectRequirement(
                    capability_id=req.capability_id,
                    weight=req.weight,
                    critical=req.critical,
                )
                for req in reqs
            ],
        )

    def _project_to_legacy(self, row: Project) -> ProjectRequirements:
        domain = self._project_to_domain(row)
        cap_rows = {
            cap.capability_id: cap.name
            for cap in self._session.scalars(select(Capability)).all()
        }
        return ProjectRequirements(
            name=row.name,
            required_skills=[
                cap_rows.get(req.capability_id, req.capability_id)
                for req in domain.requirements
            ],
            description=row.description or "",
        )


class SqlAssessmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: AssessmentRecord) -> None:
        self._session.add(
            Assessment(
                assessment_record_id=record.assessment_record_id,
                assessment_id=record.assessment_id,
                project_id=record.project_id,
                policy_version=record.policy_version,
                schema_version=record.schema_version,
                input_snapshot=record.input_snapshot,
                input_snapshot_hash=record.input_snapshot_hash,
                result_snapshot=record.result_snapshot,
                result_snapshot_hash=record.result_snapshot_hash,
                readiness_score=record.readiness_score,
                confidence_score=record.confidence_score,
                confidence_level=record.confidence_level,
                created_at=record.created_at,
                actor_reference=record.actor_reference,
            )
        )

    def add_risk_projections(self, record_id: UUID, findings: list[dict]) -> None:
        for finding in findings:
            self._session.add(
                AssessmentRiskFinding(
                    assessment_record_id=record_id,
                    finding_type=finding["finding_type"],
                    severity=finding["severity"],
                    capability_id=finding.get("capability_id"),
                    engineer_id=finding.get("engineer_id"),
                    message=finding["message"],
                )
            )

    def add_trace_projections(self, record_id: UUID, traces: list[dict]) -> None:
        for index, trace in enumerate(traces):
            self._session.add(
                AssessmentDecisionTrace(
                    assessment_record_id=record_id,
                    step=trace["step"],
                    component=trace["component"],
                    label=trace["label"],
                    value=trace["value"],
                    contribution=trace["contribution"],
                    policy_version=trace["policy_version"],
                    sort_order=index,
                )
            )

    def get_by_record_id(self, record_id: UUID) -> AssessmentRecord:
        row = self._session.get(Assessment, record_id)
        if row is None:
            raise RecordNotFoundError(f"Assessment record '{record_id}' not found")
        return _to_assessment_record(row)

    def list(
        self,
        *,
        project_id: str | None = None,
        assessment_id: str | None = None,
        review_state: HumanReviewState | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedAssessmentList:
        query = select(Assessment)
        count_query = select(func.count()).select_from(Assessment)
        if project_id:
            query = query.where(Assessment.project_id == project_id.strip().lower())
            count_query = count_query.where(Assessment.project_id == project_id.strip().lower())
        if assessment_id:
            query = query.where(Assessment.assessment_id == assessment_id)
            count_query = count_query.where(Assessment.assessment_id == assessment_id)
        if review_state is not None:
            latest_review_subq = (
                select(HumanReview.state)
                .where(HumanReview.assessment_record_id == Assessment.assessment_record_id)
                .order_by(HumanReview.created_at.desc(), HumanReview.review_id.desc())
                .limit(1)
                .correlate(Assessment)
                .scalar_subquery()
            )
            query = query.where(latest_review_subq == review_state.value)
            count_query = count_query.where(latest_review_subq == review_state.value)

        total = self._session.scalar(count_query) or 0
        rows = self._session.scalars(
            query.order_by(Assessment.created_at.desc(), Assessment.assessment_record_id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        items = []
        for row in rows:
            latest = self._session.scalar(
                select(HumanReview)
                .where(HumanReview.assessment_record_id == row.assessment_record_id)
                .order_by(HumanReview.created_at.desc(), HumanReview.review_id.desc())
                .limit(1)
            )
            items.append(
                AssessmentListItem(
                    assessment_record_id=row.assessment_record_id,
                    assessment_id=row.assessment_id,
                    project_id=row.project_id,
                    readiness_score=row.readiness_score,
                    confidence_score=row.confidence_score,
                    confidence_level=row.confidence_level,
                    policy_version=row.policy_version,
                    created_at=row.created_at,
                    latest_review_state=HumanReviewState(latest.state) if latest else None,
                )
            )
        return PaginatedAssessmentList(items=items, total=total, limit=limit, offset=offset)

    def list_by_deterministic_id(self, assessment_id: str) -> list[AssessmentRecord]:
        rows = self._session.scalars(
            select(Assessment)
            .where(Assessment.assessment_id == assessment_id)
            .order_by(Assessment.created_at.desc())
        ).all()
        return [_to_assessment_record(row) for row in rows]


class SqlSimulationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: SimulationRecord) -> None:
        self._session.add(
            Simulation(
                simulation_record_id=record.simulation_record_id,
                simulation_id=record.simulation_id,
                project_id=record.project_id,
                operation_type=record.operation_type,
                policy_version=record.policy_version,
                schema_version=record.schema_version,
                input_snapshot=record.input_snapshot,
                input_snapshot_hash=record.input_snapshot_hash,
                baseline_snapshot=record.baseline_snapshot,
                baseline_snapshot_hash=record.baseline_snapshot_hash,
                proposed_snapshot=record.proposed_snapshot,
                proposed_snapshot_hash=record.proposed_snapshot_hash,
                result_snapshot=record.result_snapshot,
                result_snapshot_hash=record.result_snapshot_hash,
                readiness_delta=record.readiness_delta,
                confidence_delta=record.confidence_delta,
                created_at=record.created_at,
                actor_reference=record.actor_reference,
            )
        )

    def get_by_record_id(self, record_id: UUID) -> SimulationRecord:
        row = self._session.get(Simulation, record_id)
        if row is None:
            raise RecordNotFoundError(f"Simulation record '{record_id}' not found")
        return _to_simulation_record(row)

    def list(
        self,
        *,
        project_id: str | None = None,
        simulation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedSimulationList:
        query = select(Simulation)
        count_query = select(func.count()).select_from(Simulation)
        if project_id:
            query = query.where(Simulation.project_id == project_id.strip().lower())
            count_query = count_query.where(Simulation.project_id == project_id.strip().lower())
        if simulation_id:
            query = query.where(Simulation.simulation_id == simulation_id)
            count_query = count_query.where(Simulation.simulation_id == simulation_id)
        total = self._session.scalar(count_query) or 0
        rows = self._session.scalars(
            query.order_by(Simulation.created_at.desc(), Simulation.simulation_record_id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        items = [
            SimulationListItem(
                simulation_record_id=row.simulation_record_id,
                simulation_id=row.simulation_id,
                project_id=row.project_id,
                operation_type=row.operation_type,
                readiness_delta=row.readiness_delta,
                confidence_delta=row.confidence_delta,
                policy_version=row.policy_version,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return PaginatedSimulationList(items=items, total=total, limit=limit, offset=offset)

    def list_by_deterministic_id(self, simulation_id: str) -> list[SimulationRecord]:
        rows = self._session.scalars(
            select(Simulation)
            .where(Simulation.simulation_id == simulation_id)
            .order_by(Simulation.created_at.desc())
        ).all()
        return [_to_simulation_record(row) for row in rows]


class SqlHumanReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, review: HumanReviewRecord) -> None:
        self._session.add(
            HumanReview(
                review_id=review.review_id,
                assessment_record_id=review.assessment_record_id,
                state=review.state.value,
                override_reason=review.override_reason,
                comment=review.comment,
                reviewer_reference=review.reviewer_reference,
                created_at=review.created_at,
                schema_version=review.schema_version,
            )
        )

    def list_for_assessment(self, record_id: UUID) -> list[HumanReviewRecord]:
        rows = self._session.scalars(
            select(HumanReview)
            .where(HumanReview.assessment_record_id == record_id)
            .order_by(HumanReview.created_at.asc(), HumanReview.review_id.asc())
        ).all()
        return [self._to_record(row) for row in rows]

    def get_latest_for_assessment(self, record_id: UUID) -> HumanReviewRecord | None:
        row = self._session.scalar(
            select(HumanReview)
            .where(HumanReview.assessment_record_id == record_id)
            .order_by(HumanReview.created_at.desc(), HumanReview.review_id.desc())
            .limit(1)
        )
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: HumanReview) -> HumanReviewRecord:
        return HumanReviewRecord(
            review_id=row.review_id,
            assessment_record_id=row.assessment_record_id,
            state=HumanReviewState(row.state),
            override_reason=row.override_reason,
            comment=row.comment,
            reviewer_reference=row.reviewer_reference,
            created_at=row.created_at,
            schema_version=row.schema_version,
        )


class SqlAuditEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: AuditEventRecord) -> None:
        self._session.add(
            AuditEvent(
                audit_event_id=event.audit_event_id,
                event_type=event.event_type.value,
                aggregate_type=event.aggregate_type.value,
                aggregate_record_id=event.aggregate_record_id,
                actor_reference=event.actor_reference,
                event_version=event.event_version,
                metadata_json=event.metadata,
                payload_hash=event.payload_hash,
                occurred_at=event.occurred_at,
            )
        )

    def list_for_aggregate(
        self,
        aggregate_type: str,
        aggregate_record_id: UUID,
    ) -> list[AuditEventRecord]:
        rows = self._session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.aggregate_type == aggregate_type,
                AuditEvent.aggregate_record_id == aggregate_record_id,
            )
            .order_by(AuditEvent.occurred_at.asc())
        ).all()
        return [self._to_record(row) for row in rows]

    @staticmethod
    def _to_record(row: AuditEvent) -> AuditEventRecord:
        from app.domain.enums import AuditAggregateType, AuditEventType

        return AuditEventRecord(
            audit_event_id=row.audit_event_id,
            event_type=AuditEventType(row.event_type),
            aggregate_type=AuditAggregateType(row.aggregate_type),
            aggregate_record_id=row.aggregate_record_id,
            actor_reference=row.actor_reference,
            event_version=row.event_version,
            metadata=row.metadata_json,
            payload_hash=row.payload_hash,
            occurred_at=row.occurred_at,
        )
