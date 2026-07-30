"""Canonical evidence-package hashing for Chief of Staff."""

from __future__ import annotations

from app.domain.chief_of_staff_constants import FALLBACK_TEMPLATE_VERSION, OUTPUT_SCHEMA_VERSION
from app.domain.chief_of_staff_models import ChiefOfStaffBrief, ChiefOfStaffEvidencePackage
from app.services.persistence.snapshot_service import canonical_json, snapshot_hash


def package_to_canonical_dict(package: ChiefOfStaffEvidencePackage) -> dict:
    data = package.model_dump(mode="json")
    # Hash excludes package_hash itself to avoid circular identity.
    data.pop("package_hash", None)
    return data


def compute_package_hash(package: ChiefOfStaffEvidencePackage) -> str:
    return snapshot_hash(package_to_canonical_dict(package))


def attach_package_hash(package: ChiefOfStaffEvidencePackage) -> ChiefOfStaffEvidencePackage:
    digest = compute_package_hash(package)
    return package.model_copy(update={"package_hash": digest})


def compute_brief_output_hash(
    brief: ChiefOfStaffBrief,
    *,
    evidence_package_hash: str,
    fallback_template_version: str | None = None,
    output_schema_version: str | None = None,
) -> str:
    """Hash semantic brief identity.

    Excludes database IDs, run/brief IDs, timestamps and durations. Citations in
    ``brief`` must reference the content-canonical ``evidence_package_hash``, not
    a persistence snapshot primary key.
    """
    envelope = {
        "evidence_package_hash": evidence_package_hash,
        "fallback_template_version": (
            FALLBACK_TEMPLATE_VERSION
            if fallback_template_version is None
            else fallback_template_version
        ),
        "output_schema_version": output_schema_version
        or brief.schema_version
        or OUTPUT_SCHEMA_VERSION,
        "brief": brief.model_dump(mode="json"),
    }
    return snapshot_hash(envelope)


def package_canonical_json(package: ChiefOfStaffEvidencePackage) -> str:
    return canonical_json(package_to_canonical_dict(package))
