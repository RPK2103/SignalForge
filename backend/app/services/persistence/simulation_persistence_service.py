"""Compute-and-persist simulation application service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.enums import AuditAggregateType, AuditEventType
from app.domain.persistence_models import (
    SNAPSHOT_SCHEMA_VERSION,
    AuditEventRecord,
    PaginatedSimulationList,
    SimulationRecord,
    SimulationRecordResponse,
)
from app.db.types import new_uuid
from app.db.unit_of_work import UnitOfWork
from app.schemas.api_v2 import SimulationRequest, SimulationResponse
from app.services.persistence.snapshot_service import (
    build_assessment_result_snapshot,
    build_simulation_input_snapshot,
    build_simulation_result_snapshot,
    snapshot_hash,
    verify_snapshot_hash,
)
from app.services.simulation_orchestrator import SimulationOrchestrator


class SimulationPersistenceService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._orchestrator = SimulationOrchestrator(catalog=uow.catalog)

    def create_simulation(
        self,
        request: SimulationRequest,
        *,
        actor_reference: str | None = None,
    ) -> SimulationRecordResponse:
        result = self._orchestrator.simulate(request)
        policy_version = result.policy_version
        input_snapshot = build_simulation_input_snapshot(
            project_id=request.project_id,
            baseline_engineer_ids=request.baseline_engineer_ids,
            operation=request.operation,
            policy_version=policy_version,
        )
        baseline_snapshot = build_assessment_result_snapshot(
            result.baseline_assessment,
            policy_version=policy_version,
        )
        proposed_snapshot = build_assessment_result_snapshot(
            result.proposed_assessment,
            policy_version=policy_version,
        )
        result_snapshot = build_simulation_result_snapshot(result, policy_version=policy_version)
        input_hash = snapshot_hash(input_snapshot)
        baseline_hash = snapshot_hash(baseline_snapshot)
        proposed_hash = snapshot_hash(proposed_snapshot)
        result_hash = snapshot_hash(result_snapshot)
        record_id = new_uuid()
        created_at = datetime.now(timezone.utc)

        record = SimulationRecord(
            simulation_record_id=record_id,
            simulation_id=result.simulation_id,
            project_id=result.project_id,
            operation_type=result.operation.type.value,
            policy_version=policy_version,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            input_snapshot=input_snapshot,
            input_snapshot_hash=input_hash,
            baseline_snapshot=baseline_snapshot,
            baseline_snapshot_hash=baseline_hash,
            proposed_snapshot=proposed_snapshot,
            proposed_snapshot_hash=proposed_hash,
            result_snapshot=result_snapshot,
            result_snapshot_hash=result_hash,
            readiness_delta=result.readiness_score_delta,
            confidence_delta=result.confidence_delta,
            created_at=created_at,
            actor_reference=actor_reference,
        )

        def _persist(uow: UnitOfWork) -> SimulationRecordResponse:
            uow.simulations.add(record)
            uow.audit_events.append(
                AuditEventRecord(
                    audit_event_id=uuid4(),
                    event_type=AuditEventType.SIMULATION_CREATED,
                    aggregate_type=AuditAggregateType.SIMULATION,
                    aggregate_record_id=record_id,
                    actor_reference=actor_reference,
                    event_version="1",
                    metadata={
                        "simulation_id": result.simulation_id,
                        "project_id": result.project_id,
                        "policy_version": policy_version,
                        "result_snapshot_hash": result_hash,
                    },
                    payload_hash=result_hash,
                    occurred_at=created_at,
                )
            )
            return SimulationRecordResponse(
                simulation_record_id=record_id,
                simulation_id=result.simulation_id,
                project_id=result.project_id,
                operation_type=result.operation.type.value,
                policy_version=policy_version,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                created_at=created_at,
                input_snapshot_hash=input_hash,
                baseline_snapshot_hash=baseline_hash,
                proposed_snapshot_hash=proposed_hash,
                result_snapshot_hash=result_hash,
                result=result,
            )

        return self._uow.execute(_persist)

    def get_simulation(self, record_id: UUID) -> SimulationRecordResponse:
        record = self._uow.simulations.get_by_record_id(record_id)
        verify_snapshot_hash(record.input_snapshot, record.input_snapshot_hash)
        verify_snapshot_hash(record.baseline_snapshot, record.baseline_snapshot_hash)
        verify_snapshot_hash(record.proposed_snapshot, record.proposed_snapshot_hash)
        verify_snapshot_hash(record.result_snapshot, record.result_snapshot_hash)
        result = SimulationResponse.model_validate(record.result_snapshot["data"])
        return SimulationRecordResponse(
            simulation_record_id=record.simulation_record_id,
            simulation_id=record.simulation_id,
            project_id=record.project_id,
            operation_type=record.operation_type,
            policy_version=record.policy_version,
            schema_version=record.schema_version,
            created_at=record.created_at,
            input_snapshot_hash=record.input_snapshot_hash,
            baseline_snapshot_hash=record.baseline_snapshot_hash,
            proposed_snapshot_hash=record.proposed_snapshot_hash,
            result_snapshot_hash=record.result_snapshot_hash,
            result=result,
        )

    def list_simulations(
        self,
        *,
        project_id: str | None = None,
        simulation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedSimulationList:
        return self._uow.simulations.list(
            project_id=project_id,
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
        )
