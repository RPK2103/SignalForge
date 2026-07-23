"""Strict Leadership Brief JSON parsing."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.domain.leadership_brief_models import LeadershipBrief
from app.services.leadership_brief.provider_interface import (
    ProviderMalformedOutputError,
    ProviderSchemaError,
)


_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _strip_markdown_fence(content: str) -> str:
    stripped = content.strip()
    match = _FENCE_PATTERN.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def parse_leadership_brief(content: str) -> LeadershipBrief:
    if not content or not content.strip():
        raise ProviderMalformedOutputError("empty provider output")

    candidate = _strip_markdown_fence(content)
    if candidate != content.strip():
        raise ProviderMalformedOutputError("markdown-fenced output is not accepted")

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProviderMalformedOutputError("provider output is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ProviderMalformedOutputError("provider output must be a JSON object")

    try:
        return LeadershipBrief.model_validate(payload)
    except ValidationError as exc:
        raise ProviderSchemaError(str(exc)) from exc
