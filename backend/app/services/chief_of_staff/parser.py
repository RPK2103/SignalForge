"""Strict JSON parser for Chief of Staff briefs."""

from __future__ import annotations

import json
import re

from app.domain.chief_of_staff_constants import MAX_PROVIDER_OUTPUT_CHARS
from app.domain.chief_of_staff_models import ChiefOfStaffBrief
from app.services.chief_of_staff.provider_interface import (
    CosProviderMalformedOutputError,
    CosProviderSchemaError,
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def parse_chief_of_staff_brief(raw_content: str) -> ChiefOfStaffBrief:
    if raw_content is None or not str(raw_content).strip():
        raise CosProviderMalformedOutputError("empty provider output")
    text = str(raw_content).strip()
    if len(text) > MAX_PROVIDER_OUTPUT_CHARS:
        raise CosProviderMalformedOutputError("oversized provider output")
    if "```" in text:
        # Existing Phase 2 convention: reject markdown-fenced output.
        raise CosProviderMalformedOutputError("markdown-fenced output rejected")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CosProviderMalformedOutputError("malformed JSON") from exc
    if not isinstance(payload, dict):
        raise CosProviderSchemaError("provider output must be a JSON object")
    try:
        return ChiefOfStaffBrief.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — map to schema error
        raise CosProviderSchemaError(f"schema validation failed: {exc}") from exc
