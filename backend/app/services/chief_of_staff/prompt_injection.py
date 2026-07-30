"""Prompt-injection detection for untrusted evidence text."""

from __future__ import annotations

from app.domain.chief_of_staff_constants import PROMPT_INJECTION_MARKERS
from app.domain.chief_of_staff_models import ChiefOfStaffEvidencePackage


def scan_text_for_injection(text: str) -> list[str]:
    lowered = (text or "").lower()
    return [marker for marker in PROMPT_INJECTION_MARKERS if marker in lowered]


def scan_package_for_injection(package: ChiefOfStaffEvidencePackage) -> list[str]:
    hits: list[str] = []
    texts = [
        package.target_lifecycle.display_name,
        *[e.summary for e in package.evidence_entries],
        *package.missing_data_warnings,
        *package.contradiction_warnings,
    ]
    for text in texts:
        for marker in scan_text_for_injection(text):
            if marker not in hits:
                hits.append(marker)
    return hits


def normalize_untrusted_text(text: str, limit: int) -> str:
    """Length-bound and strip control characters; treat as data not instructions."""
    cleaned = "".join(ch for ch in (text or "") if ch == "\n" or (ord(ch) >= 32))
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned
