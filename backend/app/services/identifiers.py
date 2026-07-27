"""Public deterministic identifier builders shared across readiness and simulation."""

import hashlib
import json

from app.domain.enums import SimulationOperationType
from app.domain.simulation_models import SimulationOperation


def _normalize_engineer_ids(engineer_ids: list[str]) -> list[str]:
    return sorted(
        {engineer_id.strip().lower() for engineer_id in engineer_ids if engineer_id.strip()}
    )


def build_assessment_id(
    project_id: str,
    engineer_ids: list[str],
    policy_version: str,
) -> str:
    """Build a stable fingerprint from canonical readiness request inputs."""
    canonical = {
        "project_id": project_id.strip().lower(),
        "engineer_ids": _normalize_engineer_ids(engineer_ids),
        "policy_version": policy_version,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _canonical_operation(operation: SimulationOperation) -> dict:
    payload = operation.model_dump(mode="json")
    if operation.type == SimulationOperationType.COMPARE:
        payload["proposed_engineer_ids"] = _normalize_engineer_ids(
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
    """Build a stable fingerprint from canonical simulation request inputs."""
    canonical = {
        "project_id": project_id.strip().lower(),
        "baseline_engineer_ids": _normalize_engineer_ids(baseline_engineer_ids),
        "operation": _canonical_operation(operation),
        "proposed_engineer_ids": _normalize_engineer_ids(proposed_engineer_ids),
        "policy_version": policy_version,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
