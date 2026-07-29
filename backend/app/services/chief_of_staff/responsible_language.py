"""Responsible-language validation for Chief of Staff output."""

from __future__ import annotations

from app.domain.chief_of_staff_constants import PROHIBITED_LANGUAGE_MARKERS
from app.domain.chief_of_staff_models import ChiefOfStaffBrief
from app.domain.prediction_enums import EstimateKind


class ResponsibleLanguageError(ValueError):
    pass


def validate_responsible_language(brief: ChiefOfStaffBrief) -> None:
    texts: list[str] = []
    for section in brief.sections:
        texts.append(section.text)
    for claim in brief.claims:
        texts.append(claim.text)
    texts.extend(brief.limitations)

    blob = "\n".join(texts).lower()

    for marker in PROHIBITED_LANGUAGE_MARKERS:
        if marker in blob:
            raise ResponsibleLanguageError(f"Prohibited language detected: {marker}")

    # Structured semantic checks (primary control).
    if brief.estimate_kind == EstimateKind.UNCALIBRATED_SCORE:
        if brief.probability is not None:
            raise ResponsibleLanguageError(
                "Uncalibrated score must not populate probability"
            )
        if "calibrated probability" in blob and "not a calibrated" not in blob:
            # Allow explicit negation; reject affirmative calibrated claims.
            if "is a calibrated" in blob or "calibrated probability of" in blob:
                raise ResponsibleLanguageError(
                    "Uncalibrated score described as calibrated probability"
                )

    if any(
        phrase in blob
        for phrase in (
            "readiness probability",
            "readiness is a probability",
            "assessment confidence probability",
            "graph confidence is model confidence",
        )
    ):
        raise ResponsibleLanguageError("Confidence/readiness mislabeled as probability")

    if "candidate model is active" in blob or "rejected model is active" in blob:
        raise ResponsibleLanguageError("Non-active model described as active")

    if brief.fallback_visible and "calibrated fallback" in blob:
        raise ResponsibleLanguageError("Fallback described as calibrated")
