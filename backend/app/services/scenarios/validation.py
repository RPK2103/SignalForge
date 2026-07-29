"""Scenario assumption validation (Phase 3 Prompt 5).

Rejects secrets/PII, contradictory assumptions, unbounded payloads, and
unsupported scenario kinds. No LLM validation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.domain.scenario_constants import (
    FORBIDDEN_ASSUMPTION_TOKENS,
    MAX_ASSUMPTION_PAYLOAD_BYTES,
    MAX_COMBINED_CHANGES,
    MAX_DEADLINE_COMPRESSION_DAYS,
    MAX_DELAY_DAYS,
    MAX_REDUCTION_PERCENTAGE,
    MAX_SCENARIO_CHANGES,
    MAX_SUBJECT_IDS_PER_CHANGE,
    MAX_UNAVAILABILITY_DAYS,
    MIN_DEADLINE_COMPRESSION_DAYS,
    MIN_DELAY_DAYS,
    MIN_REDUCTION_PERCENTAGE,
    SCENARIO_SCHEMA_VERSION,
)
from app.domain.scenario_enums import ScenarioKind
from app.services.enterprise.exceptions import EnterpriseValidationError
from app.services.persistence.snapshot_service import snapshot_hash


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_dt(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    if not isinstance(value, str) or not value.strip():
        raise EnterpriseValidationError(f"{field} must be an ISO-8601 datetime")
    raw = value.strip().replace("Z", "+00:00")
    try:
        return _aware(datetime.fromisoformat(raw))
    except ValueError as exc:
        raise EnterpriseValidationError(f"{field} must be an ISO-8601 datetime") from exc


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EnterpriseValidationError(f"{key} is required")
    return value.strip()


def _require_int(payload: dict[str, Any], key: str, *, lo: int, hi: int) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnterpriseValidationError(f"{key} must be an integer between {lo} and {hi}")
    if value < lo or value > hi:
        raise EnterpriseValidationError(f"{key} must be between {lo} and {hi}")
    return value


def _scan_forbidden(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            for token in FORBIDDEN_ASSUMPTION_TOKENS:
                if token in key_l:
                    raise EnterpriseValidationError(
                        f"Assumption key contains forbidden token '{token}'"
                    )
            _scan_forbidden(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _scan_forbidden(item, f"{path}[{idx}]")
    elif isinstance(obj, str):
        lower = obj.lower()
        for token in FORBIDDEN_ASSUMPTION_TOKENS:
            if token in lower and ("@" in obj or "://" in obj or "BEGIN " in obj.upper()):
                raise EnterpriseValidationError(
                    f"Assumption value appears to contain forbidden data near '{token}'"
                )


def _bounded_payload(assumptions: dict[str, Any]) -> None:
    encoded = json.dumps(assumptions, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) > MAX_ASSUMPTION_PAYLOAD_BYTES:
        raise EnterpriseValidationError(
            f"Assumption payload exceeds {MAX_ASSUMPTION_PAYLOAD_BYTES} bytes"
        )


def _validate_interval(start: datetime, end: datetime, *, max_days: int) -> None:
    if end <= start:
        raise EnterpriseValidationError("unavailable_until must be after unavailable_from")
    if (end - start).days > max_days:
        raise EnterpriseValidationError(f"Interval duration must be <= {max_days} days")


def normalize_assumptions(kind: ScenarioKind | str, assumptions: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize assumptions into a deterministic dict."""
    if isinstance(kind, str):
        try:
            kind = ScenarioKind(kind)
        except ValueError as exc:
            raise EnterpriseValidationError(f"Unsupported scenario kind: {kind}") from exc
    if not isinstance(assumptions, dict):
        raise EnterpriseValidationError("assumptions must be an object")
    _scan_forbidden(assumptions)
    _bounded_payload(assumptions)

    # Idempotent: already-normalized payloads keep a changes list.
    if (
        assumptions.get("schema_version") == SCENARIO_SCHEMA_VERSION
        and isinstance(assumptions.get("changes"), list)
        and assumptions.get("kind") == kind.value
    ):
        if kind == ScenarioKind.COMBINED:
            return _normalize_combined({"changes": assumptions["changes"]})
        if len(assumptions["changes"]) == 1:
            return {
                "schema_version": SCENARIO_SCHEMA_VERSION,
                "kind": kind.value,
                "changes": [_normalize_single(kind, assumptions["changes"][0])],
            }

    if kind == ScenarioKind.COMBINED:
        return _normalize_combined(assumptions)

    change = _normalize_single(kind, assumptions)
    return {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "kind": kind.value,
        "changes": [change],
    }


def _normalize_single(kind: ScenarioKind, payload: dict[str, Any]) -> dict[str, Any]:
    # Allow either flat payload or {"kind": ..., ...} / nested under "change".
    body = dict(payload)
    if "change" in body and isinstance(body["change"], dict):
        body = dict(body["change"])
    body.pop("schema_version", None)
    body.pop("changes", None)
    if body.get("kind") and body["kind"] != kind.value:
        raise EnterpriseValidationError("Nested kind does not match scenario kind")
    body["kind"] = kind.value

    if kind == ScenarioKind.ENGINEER_UNAVAILABLE:
        engineer_id = _require_str(body, "engineer_id")
        start = _parse_dt(body.get("unavailable_from"), "unavailable_from")
        end = _parse_dt(body.get("unavailable_until"), "unavailable_until")
        _validate_interval(start, end, max_days=MAX_UNAVAILABILITY_DAYS)
        return {
            "kind": kind.value,
            "engineer_id": engineer_id,
            "unavailable_from": start.isoformat(),
            "unavailable_until": end.isoformat(),
        }

    if kind == ScenarioKind.TEAM_CAPACITY_REDUCTION:
        team_id = _require_str(body, "team_id")
        pct = _require_int(
            body,
            "reduction_percentage",
            lo=MIN_REDUCTION_PERCENTAGE,
            hi=MAX_REDUCTION_PERCENTAGE,
        )
        start = _parse_dt(body.get("effective_from"), "effective_from")
        end = _parse_dt(body.get("effective_until"), "effective_until")
        _validate_interval(start, end, max_days=MAX_UNAVAILABILITY_DAYS)
        return {
            "kind": kind.value,
            "team_id": team_id,
            "reduction_percentage": pct,
            "effective_from": start.isoformat(),
            "effective_until": end.isoformat(),
        }

    if kind == ScenarioKind.CAPABILITY_UNAVAILABLE:
        capability_id = _require_str(body, "capability_id")
        start = _parse_dt(body.get("unavailable_from"), "unavailable_from")
        end = _parse_dt(body.get("unavailable_until"), "unavailable_until")
        _validate_interval(start, end, max_days=MAX_UNAVAILABILITY_DAYS)
        owner_ids = body.get("affected_owner_ids") or []
        if not isinstance(owner_ids, list):
            raise EnterpriseValidationError("affected_owner_ids must be a list")
        if len(owner_ids) > MAX_SUBJECT_IDS_PER_CHANGE:
            raise EnterpriseValidationError("Too many affected_owner_ids")
        cleaned = sorted({str(x).strip() for x in owner_ids if str(x).strip()})
        return {
            "kind": kind.value,
            "capability_id": capability_id,
            "unavailable_from": start.isoformat(),
            "unavailable_until": end.isoformat(),
            "affected_owner_ids": cleaned,
        }

    if kind == ScenarioKind.REPOSITORY_UNAVAILABLE:
        repository_id = _require_str(body, "repository_id")
        start = _parse_dt(body.get("unavailable_from"), "unavailable_from")
        end = _parse_dt(body.get("unavailable_until"), "unavailable_until")
        _validate_interval(start, end, max_days=MAX_UNAVAILABILITY_DAYS)
        return {
            "kind": kind.value,
            "repository_id": repository_id,
            "unavailable_from": start.isoformat(),
            "unavailable_until": end.isoformat(),
        }

    if kind == ScenarioKind.DEPENDENCY_DELAY:
        dependency_id = _require_str(body, "dependency_id")
        delay_days = _require_int(body, "delay_days", lo=MIN_DELAY_DAYS, hi=MAX_DELAY_DAYS)
        return {
            "kind": kind.value,
            "dependency_id": dependency_id,
            "delay_days": delay_days,
        }

    if kind == ScenarioKind.DEADLINE_COMPRESSION:
        project_id = _require_str(body, "project_id")
        days_reduced = _require_int(
            body,
            "days_reduced",
            lo=MIN_DEADLINE_COMPRESSION_DAYS,
            hi=MAX_DEADLINE_COMPRESSION_DAYS,
        )
        return {
            "kind": kind.value,
            "project_id": project_id,
            "days_reduced": days_reduced,
        }

    if kind == ScenarioKind.INCIDENT_ESCALATION:
        start = _parse_dt(body.get("effective_from"), "effective_from")
        end = _parse_dt(body.get("effective_until"), "effective_until")
        _validate_interval(start, end, max_days=MAX_UNAVAILABILITY_DAYS)
        severity = _require_str(body, "simulated_severity").lower()
        if severity not in {"low", "medium", "high", "critical"}:
            raise EnterpriseValidationError("simulated_severity must be low|medium|high|critical")
        incident_id = body.get("incident_id")
        repository_id = body.get("repository_id")
        project_id = body.get("project_id")
        if not any(
            isinstance(x, str) and x.strip() for x in (incident_id, repository_id, project_id)
        ):
            raise EnterpriseValidationError(
                "incident_escalation requires incident_id, repository_id, or project_id"
            )
        result: dict[str, Any] = {
            "kind": kind.value,
            "simulated_severity": severity,
            "effective_from": start.isoformat(),
            "effective_until": end.isoformat(),
        }
        if isinstance(incident_id, str) and incident_id.strip():
            result["incident_id"] = incident_id.strip()
        if isinstance(repository_id, str) and repository_id.strip():
            result["repository_id"] = repository_id.strip()
        if isinstance(project_id, str) and project_id.strip():
            result["project_id"] = project_id.strip()
        return result

    raise EnterpriseValidationError(f"Unsupported scenario kind: {kind}")


def _change_signature(change: dict[str, Any]) -> str:
    return snapshot_hash(change)


def _normalize_combined(assumptions: dict[str, Any]) -> dict[str, Any]:
    changes_raw = assumptions.get("changes")
    if not isinstance(changes_raw, list) or not changes_raw:
        raise EnterpriseValidationError("combined scenarios require a non-empty changes list")
    if len(changes_raw) > MAX_COMBINED_CHANGES or len(changes_raw) > MAX_SCENARIO_CHANGES:
        raise EnterpriseValidationError(f"At most {MAX_COMBINED_CHANGES} combined changes allowed")

    normalized: list[dict[str, Any]] = []
    signatures: set[str] = set()
    subjects: dict[str, set[str]] = {}

    for raw in changes_raw:
        if not isinstance(raw, dict):
            raise EnterpriseValidationError("Each combined change must be an object")
        nested_kind = raw.get("kind")
        if nested_kind == ScenarioKind.COMBINED.value:
            raise EnterpriseValidationError("Recursive combined scenarios are not allowed")
        try:
            kind = ScenarioKind(str(nested_kind))
        except ValueError as exc:
            raise EnterpriseValidationError(
                f"Unsupported nested scenario kind: {nested_kind}"
            ) from exc
        change = _normalize_single(kind, raw)
        sig = _change_signature(change)
        if sig in signatures:
            raise EnterpriseValidationError("Duplicate identical changes are not allowed")
        signatures.add(sig)
        _check_contradiction(subjects, change)
        normalized.append(change)

    normalized.sort(key=_change_signature)
    return {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "kind": ScenarioKind.COMBINED.value,
        "changes": normalized,
    }


def _check_contradiction(subjects: dict[str, set[str]], change: dict[str, Any]) -> None:
    kind = change["kind"]
    key_map = {
        ScenarioKind.ENGINEER_UNAVAILABLE.value: ("engineer", change.get("engineer_id")),
        ScenarioKind.TEAM_CAPACITY_REDUCTION.value: ("team", change.get("team_id")),
        ScenarioKind.CAPABILITY_UNAVAILABLE.value: ("capability", change.get("capability_id")),
        ScenarioKind.REPOSITORY_UNAVAILABLE.value: ("repository", change.get("repository_id")),
        ScenarioKind.DEPENDENCY_DELAY.value: ("dependency", change.get("dependency_id")),
        ScenarioKind.DEADLINE_COMPRESSION.value: ("project_deadline", change.get("project_id")),
        ScenarioKind.INCIDENT_ESCALATION.value: (
            "incident",
            change.get("incident_id") or change.get("repository_id") or change.get("project_id"),
        ),
    }
    bucket, subject = key_map.get(kind, (kind, None))
    if subject is None:
        return
    used = subjects.setdefault(bucket, set())
    if subject in used:
        raise EnterpriseValidationError(
            f"Contradictory or duplicate assumptions for {bucket}={subject}"
        )
    used.add(str(subject))


def specification_hash(
    *,
    tenant_id: str,
    scenario_kind: ScenarioKind | str,
    target_type: str,
    target_id: str,
    assumptions: dict[str, Any],
    schema_version: str = SCENARIO_SCHEMA_VERSION,
) -> str:
    kind = scenario_kind.value if isinstance(scenario_kind, ScenarioKind) else scenario_kind
    normalized = normalize_assumptions(kind, assumptions)
    return snapshot_hash(
        {
            "tenant_id": tenant_id,
            "scenario_kind": kind,
            "target_type": target_type,
            "target_id": target_id,
            "schema_version": schema_version,
            "assumptions": normalized,
        }
    )
