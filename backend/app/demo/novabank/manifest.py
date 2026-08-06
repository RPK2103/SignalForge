"""Canonical NovaBank demo manifest hashing and persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import enterprise as orm
from app.demo.novabank.constants import (
    AS_OF_AT,
    DATASET_NAME,
    DATASET_VERSION,
    GENERATOR_VERSION,
    MANIFEST_SIGNAL_TYPE,
    MANIFEST_SOURCE_RECORD_ID,
    SCHEMA_COMPAT,
    SYNTHETIC_DISCLAIMER,
    TENANT_ID,
)
from app.demo.novabank.helpers import ensure, tid
from app.demo.novabank.specification import CANONICAL_SPEC, TARGET_INVENTORY
from app.services.persistence.snapshot_service import snapshot_hash

_COUNT_MODELS: list[tuple[str, type, Any]] = [
    ("organizations", orm.Organization, orm.Organization.organization_id),
    ("business_units", orm.BusinessUnit, orm.BusinessUnit.business_unit_id),
    ("departments", orm.Department, orm.Department.department_id),
    ("teams", orm.Team, orm.Team.team_id),
    ("engineers", orm.EngineerProfile, orm.EngineerProfile.engineer_profile_id),
    ("capabilities", orm.EnterpriseCapability, orm.EnterpriseCapability.capability_id),
    ("skills", orm.EnterpriseSkill, orm.EnterpriseSkill.skill_id),
    ("initiatives", orm.Initiative, orm.Initiative.initiative_id),
    ("projects", orm.EnterpriseProject, orm.EnterpriseProject.enterprise_project_id),
    ("repositories", orm.Repository, orm.Repository.repository_id),
    ("sprints", orm.Sprint, orm.Sprint.sprint_id),
    ("work_items", orm.WorkItem, orm.WorkItem.work_item_id),
    ("pull_requests", orm.PullRequest, orm.PullRequest.pull_request_id),
    ("deployments", orm.Deployment, orm.Deployment.deployment_id),
    ("incidents", orm.Incident, orm.Incident.incident_id),
    ("dependencies", orm.Dependency, orm.Dependency.dependency_id),
    ("ownership", orm.Ownership, orm.Ownership.ownership_id),
    ("availability", orm.Availability, orm.Availability.availability_id),
]


def collect_inventory(session: Session) -> dict[str, int]:
    inventory: dict[str, int] = {}
    for key, model, _col in _COUNT_MODELS:
        rows = session.scalars(select(model).where(model.tenant_id == TENANT_ID)).all()
        inventory[key] = len(rows)
    return inventory


def collect_category_hashes(session: Session) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, model, id_col in _COUNT_MODELS:
        ids = sorted(session.scalars(select(id_col).where(model.tenant_id == TENANT_ID)).all())
        hashes[key] = snapshot_hash({"ids": ids, "count": len(ids)})
    return hashes


def build_manifest(
    session: Session,
    *,
    created: dict[str, int] | None = None,
    reused: dict[str, int] | None = None,
) -> dict[str, Any]:
    inventory = collect_inventory(session)
    category_hashes = collect_category_hashes(session)
    story_inventory = [
        {
            "story_id": story.story_id,
            "title": story.title,
            "scenario_name": story.scenario_name,
            "target_initiative_slug": story.target_initiative_slug,
            "target_project_slug": story.target_project_slug,
        }
        for story in CANONICAL_SPEC.stories
    ]
    body: dict[str, Any] = {
        "dataset_name": DATASET_NAME,
        "dataset_version": DATASET_VERSION,
        "generator_version": GENERATOR_VERSION,
        "schema_compat": SCHEMA_COMPAT,
        "as_of_at": AS_OF_AT.isoformat().replace("+00:00", "Z"),
        "target_inventory": dict(TARGET_INVENTORY),
        "realized_inventory": inventory,
        "category_hashes": category_hashes,
        "story_inventory": story_inventory,
        "synthetic_disclaimer": SYNTHETIC_DISCLAIMER,
        "production_ineligible": True,
        "known_limitations": [
            "Synthetic demonstration data only",
            "No calibrated real-world probability",
            "No Microsoft endorsement",
            "Decision-support only",
            "Uncalibrated scores are not probabilities",
        ],
        "created_counts": created or {},
        "reused_counts": reused or {},
    }
    # Manifest hash excludes its own hash field and execution metadata.
    body["manifest_hash"] = snapshot_hash(
        {k: v for k, v in body.items() if k not in {"created_counts", "reused_counts"}}
    )
    return body


def persist_manifest(session: Session, manifest: dict[str, Any], data_source_id: str) -> int:
    """Persist manifest as an EvidenceSignal (no new migration).

    Idempotent on ``MANIFEST_SOURCE_RECORD_ID``: a second identical seed reuses the
    existing signal. An incompatible stored hash raises rather than silently overwrite.
    """
    existing = session.scalars(
        select(orm.EvidenceSignal).where(
            orm.EvidenceSignal.tenant_id == TENANT_ID,
            orm.EvidenceSignal.signal_type == MANIFEST_SIGNAL_TYPE,
            orm.EvidenceSignal.source_record_id == MANIFEST_SOURCE_RECORD_ID,
        )
    ).first()
    if existing is not None:
        stored = (existing.payload or {}).get("manifest_hash")
        if stored != manifest["manifest_hash"]:
            raise ValueError(
                "Incompatible NovaBank demo manifest already present "
                f"(stored={stored}, computed={manifest['manifest_hash']})"
            )
        return 0

    run_id = tid("run", data_source_id, "demo-manifest-v2")
    ensure(
        session,
        orm.IngestionRun,
        run_id,
        {
            "ingestion_run_id": run_id,
            "data_source_id": data_source_id,
            "run_type": "backfill",
            "status": "succeeded",
            "started_at": AS_OF_AT,
            "completed_at": AS_OF_AT,
            "cursor": {"kind": "demo_manifest"},
            "records_read": 1,
            "records_written": 1,
            "records_skipped": 0,
            "error_category": "none",
            "error_summary": None,
            "processing_version": "1",
        },
    )
    stable_manifest = {
        k: v
        for k, v in manifest.items()
        if k not in {"manifest_hash", "created_counts", "reused_counts"}
    }
    payload = {
        "kind": MANIFEST_SIGNAL_TYPE,
        "manifest": stable_manifest,
        "manifest_hash": manifest["manifest_hash"],
        "synthetic": True,
        "production_ineligible": True,
    }
    payload_hash = snapshot_hash(payload)
    sig_id = tid(
        "sig",
        data_source_id,
        MANIFEST_SOURCE_RECORD_ID,
        MANIFEST_SIGNAL_TYPE,
        DATASET_VERSION,
    )
    return ensure(
        session,
        orm.EvidenceSignal,
        sig_id,
        {
            "evidence_signal_id": sig_id,
            "data_source_id": data_source_id,
            "ingestion_run_id": run_id,
            "source_record_id": MANIFEST_SOURCE_RECORD_ID,
            "signal_type": MANIFEST_SIGNAL_TYPE,
            "subject_type": "organization",
            "subject_id": tid("org", "novabank"),
            "event_time": AS_OF_AT,
            "observed_at": AS_OF_AT,
            "ingested_at": AS_OF_AT,
            "schema_version": "1",
            "processing_version": "1",
            "confidence": 1.0,
            "permission_classification": "internal",
            "expires_at": None,
            "payload": payload,
            "payload_hash": payload_hash,
            "provenance": {
                "dataset_version": DATASET_VERSION,
                "generator_version": GENERATOR_VERSION,
                "synthetic": True,
            },
        },
    )


def load_manifest(session: Session) -> dict[str, Any] | None:
    row = session.scalars(
        select(orm.EvidenceSignal)
        .where(
            orm.EvidenceSignal.tenant_id == TENANT_ID,
            orm.EvidenceSignal.signal_type == MANIFEST_SIGNAL_TYPE,
            orm.EvidenceSignal.source_record_id == MANIFEST_SOURCE_RECORD_ID,
        )
        .order_by(orm.EvidenceSignal.evidence_signal_id.asc())
    ).first()
    if row is None:
        return None
    payload = row.payload or {}
    manifest = dict(payload.get("manifest") or {})
    manifest["manifest_hash"] = payload.get("manifest_hash") or manifest.get("manifest_hash")
    return manifest
