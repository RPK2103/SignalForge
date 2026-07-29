"""Versioned prompt templates for Chief of Staff."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.chief_of_staff_constants import PROMPT_VERSION
from app.domain.chief_of_staff_models import ChiefOfStaffEvidencePackage
from app.services.chief_of_staff.canonicalization import package_canonical_json

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "prompts" / "chief_of_staff" / "v1"


class PromptTemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptBundle:
    prompt_version: str
    system_prompt: str
    user_prompt: str


def load_prompt_bundle(package: ChiefOfStaffEvidencePackage) -> PromptBundle:
    system_path = _TEMPLATE_DIR / "system.txt"
    user_path = _TEMPLATE_DIR / "user.txt"
    if not system_path.exists() or not user_path.exists():
        raise PromptTemplateError("Chief of Staff prompt templates missing")
    system_prompt = system_path.read_text(encoding="utf-8")
    user_template = user_path.read_text(encoding="utf-8")
    evidence_json = package_canonical_json(package)
    user_prompt = (
        user_template.replace("{{prompt_version}}", PROMPT_VERSION)
        .replace("{{intent}}", package.intent.value)
        .replace("{{evidence_package_json}}", evidence_json)
    )
    return PromptBundle(
        prompt_version=PROMPT_VERSION,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
