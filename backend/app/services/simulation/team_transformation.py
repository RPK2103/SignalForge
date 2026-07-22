"""Immutable team transformation for simulation operations."""

from app.domain.enums import SimulationOperationType
from app.domain.simulation_models import (
    AddSimulationOperation,
    CompareSimulationOperation,
    RemoveSimulationOperation,
    ReplaceSimulationOperation,
    SimulationOperation,
)
from app.services.simulation.exceptions import SimulationValidationError


def normalize_engineer_id(engineer_id: str) -> str:
    return engineer_id.strip().lower()


def canonicalize_engineer_ids(engineer_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    canonical: list[str] = []
    for engineer_id in engineer_ids:
        normalized = normalize_engineer_id(engineer_id)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        canonical.append(normalized)
    return canonical


class TeamTransformationService:
    def compute_proposed_ids(
        self,
        baseline_ids: list[str],
        operation: SimulationOperation,
    ) -> list[str]:
        baseline_set = set(baseline_ids)

        if operation.type == SimulationOperationType.ADD:
            assert isinstance(operation, AddSimulationOperation)
            incoming_id = normalize_engineer_id(operation.engineer_id)
            if incoming_id in baseline_set:
                raise SimulationValidationError(
                    f"Engineer '{operation.engineer_id}' is already on the baseline team.",
                    status_code=409,
                )
            return sorted(baseline_set | {incoming_id})

        if operation.type == SimulationOperationType.REMOVE:
            assert isinstance(operation, RemoveSimulationOperation)
            outgoing_id = normalize_engineer_id(operation.engineer_id)
            if outgoing_id not in baseline_set:
                raise SimulationValidationError(
                    f"Engineer '{operation.engineer_id}' is not on the baseline team.",
                    status_code=409,
                )
            return sorted(baseline_set - {outgoing_id})

        if operation.type == SimulationOperationType.REPLACE:
            assert isinstance(operation, ReplaceSimulationOperation)
            outgoing_id = normalize_engineer_id(operation.remove_engineer_id)
            incoming_id = normalize_engineer_id(operation.add_engineer_id)
            if outgoing_id not in baseline_set:
                raise SimulationValidationError(
                    f"Engineer '{operation.remove_engineer_id}' is not on the baseline team.",
                    status_code=409,
                )
            if outgoing_id == incoming_id:
                raise SimulationValidationError(
                    "Replacement incoming and outgoing engineers must differ.",
                    status_code=400,
                )
            remaining_ids = baseline_set - {outgoing_id}
            if incoming_id in remaining_ids:
                raise SimulationValidationError(
                    f"Engineer '{operation.add_engineer_id}' is already on the baseline team.",
                    status_code=409,
                )
            return sorted(remaining_ids | {incoming_id})

        assert isinstance(operation, CompareSimulationOperation)
        raw_ids = [
            normalize_engineer_id(engineer_id)
            for engineer_id in operation.proposed_engineer_ids
            if normalize_engineer_id(engineer_id)
        ]
        if len(raw_ids) != len(set(raw_ids)):
            raise SimulationValidationError(
                "Proposed engineer IDs must be logically unique.",
                status_code=400,
            )
        return sorted(set(raw_ids))
