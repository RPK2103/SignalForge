"""Deterministic simulation identifier generation."""

import hashlib
import json

from app.domain.enums import SimulationOperationType
from app.domain.simulation_models import CompareSimulationOperation, SimulationOperation


def _normalize_ids(engineer_ids: list[str]) -> list[str]:
    return sorted(
        {
            engineer_id.strip().lower()
            for engineer_id in engineer_ids
            if engineer_id.strip()
        }
    )


def _canonical_operation(operation: SimulationOperation) -> dict:
    payload = operation.model_dump(mode="json")
    if operation.type == SimulationOperationType.COMPARE:
        payload["proposed_engineer_ids"] = _normalize_ids(
            payload.get("proposed_engineer_ids", [])
        )
    return payload


def build_simulation_id(
    *,
    project_id: str,
    baseline_engineer_ids: list[str],
    operation: SimulationOperation,
    proposed_engineer_ids: list[str],
    policy_version: str,
) -> str:
    canonical = {
        "project_id": project_id.strip().lower(),
        "baseline_engineer_ids": _normalize_ids(baseline_engineer_ids),
        "operation": _canonical_operation(operation),
        "proposed_engineer_ids": _normalize_ids(proposed_engineer_ids),
        "policy_version": policy_version,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
