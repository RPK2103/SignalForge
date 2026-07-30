"""Stable opaque evidence IDs for Chief of Staff packages."""

from __future__ import annotations

import hashlib

from app.domain.chief_of_staff_enums import EvidenceEntryType


def _stable_hash(*parts: str) -> str:
    material = "|".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def build_evidence_id(
    evidence_type: EvidenceEntryType | str,
    tenant_id: str,
    source_record_id: str,
    *extra: str,
) -> str:
    type_value = evidence_type.value if hasattr(evidence_type, "value") else str(evidence_type)
    digest = _stable_hash(type_value, tenant_id, source_record_id, *extra)
    return f"{type_value}:{digest}"
