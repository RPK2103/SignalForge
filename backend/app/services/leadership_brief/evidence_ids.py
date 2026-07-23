"""Deterministic stable evidence identifiers for Leadership Brief grounding."""

from __future__ import annotations

import hashlib
import json

from app.domain.models import DecisionTraceEntry, RiskFinding


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _stable_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_risk_evidence_id(finding: RiskFinding) -> str:
    payload = {
        "finding_type": _enum_value(finding.finding_type),
        "capability_id": finding.capability_id or "",
        "engineer_id": finding.engineer_id or "",
        "severity": _enum_value(finding.severity),
        "policy_rule": _enum_value(finding.finding_type),
        "message": finding.message,
    }
    return f"risk:{_stable_hash(payload)}"


def build_trace_evidence_id(entry: DecisionTraceEntry) -> str:
    payload = {
        "step": entry.step,
        "component": entry.component,
        "label": entry.label,
        "value": entry.value,
        "contribution": entry.contribution,
        "policy_version": entry.policy_version,
        "evidence_source": entry.component,
    }
    return f"trace:{_stable_hash(payload)}"


def parse_evidence_namespace(reference_id: str) -> str:
    prefix, _, _ = reference_id.partition(":")
    return prefix
