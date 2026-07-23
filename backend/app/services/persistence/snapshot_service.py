"""Canonical snapshot serialization and integrity hashing."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from app.domain.persistence_models import SNAPSHOT_SCHEMA_VERSION
from app.services.persistence.exceptions import SnapshotIntegrityError


def _enum_to_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _normalize_for_snapshot(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return _normalize_for_snapshot(data.model_dump(mode="json"))
    if isinstance(data, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(data.keys()):
            normalized[key] = _normalize_for_snapshot(data[key])
        return normalized
    if isinstance(data, list):
        return [_normalize_for_snapshot(item) for item in data]
    return _enum_to_value(data)


def canonical_json(data: Any) -> str:
    normalized = _normalize_for_snapshot(data)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def snapshot_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def build_snapshot_payload(*, schema_version: str, policy_version: str, data: Any) -> dict:
    return {
        "schema_version": schema_version,
        "policy_version": policy_version,
        "data": _normalize_for_snapshot(data),
    }


def build_assessment_input_snapshot(
    *,
    project_id: str,
    engineer_ids: list[str],
    policy_version: str,
) -> dict:
    return build_snapshot_payload(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        policy_version=policy_version,
        data={
            "project_id": project_id.strip().lower(),
            "engineer_ids": sorted(
                {
                    engineer_id.strip().lower()
                    for engineer_id in engineer_ids
                    if engineer_id.strip()
                }
            ),
        },
    )


def build_assessment_result_snapshot(result: BaseModel, *, policy_version: str) -> dict:
    return build_snapshot_payload(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        policy_version=policy_version,
        data=result.model_dump(mode="json"),
    )


def build_simulation_input_snapshot(
    *,
    project_id: str,
    baseline_engineer_ids: list[str],
    operation: BaseModel,
    policy_version: str,
) -> dict:
    return build_snapshot_payload(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        policy_version=policy_version,
        data={
            "project_id": project_id.strip().lower(),
            "baseline_engineer_ids": sorted(
                {
                    engineer_id.strip().lower()
                    for engineer_id in baseline_engineer_ids
                    if engineer_id.strip()
                }
            ),
            "operation": operation.model_dump(mode="json"),
        },
    )


def build_simulation_result_snapshot(result: BaseModel, *, policy_version: str) -> dict:
    return build_snapshot_payload(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        policy_version=policy_version,
        data=result.model_dump(mode="json"),
    )


def verify_snapshot_hash(snapshot: dict, expected_hash: str) -> None:
    actual = snapshot_hash(snapshot)
    if actual != expected_hash:
        raise SnapshotIntegrityError("Stored snapshot failed integrity verification")
