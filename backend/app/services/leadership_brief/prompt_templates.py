"""Versioned prompt templates for Leadership Brief generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.leadership_brief.evidence_package import canonical_evidence_json
from app.domain.leadership_brief_models import LeadershipBriefEvidencePackage

PROMPT_VERSION = "leadership-brief-v1"
_TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "prompts" / "leadership_brief" / "v1"


class PromptTemplateError(Exception):
    """Prompt template loading or rendering failed."""


@dataclass(frozen=True)
class PromptBundle:
    prompt_version: str
    system_prompt: str
    user_prompt: str


def _load_template(name: str) -> str:
    path = _TEMPLATE_ROOT / name
    if not path.is_file():
        raise PromptTemplateError(f"missing prompt template: {name}")
    return path.read_text(encoding="utf-8")


def load_prompt_bundle(
    evidence_package: LeadershipBriefEvidencePackage,
) -> PromptBundle:
    system_prompt = _load_template("system.txt")
    user_template = _load_template("user.txt")
    evidence_json = canonical_evidence_json(evidence_package)
    user_prompt = user_template.replace("{{prompt_version}}", PROMPT_VERSION).replace(
        "{{evidence_package_json}}",
        evidence_json,
    )
    return PromptBundle(
        prompt_version=PROMPT_VERSION,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
