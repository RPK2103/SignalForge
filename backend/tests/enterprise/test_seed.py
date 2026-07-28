"""Determinism + idempotency tests for the NovaBank enterprise seed."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enterprise_seed import TENANT_ID, seed_enterprise
from app.db.models import enterprise as orm
from app.db.session import get_engine
from app.domain.enterprise_identifiers import build_entity_id
from app.services.persistence.snapshot_service import snapshot_hash

EXPECTED_CREATED = {
    "organizations": 1,
    "business_units": 2,
    "departments": 4,
    "teams": 6,
    "engineers": 15,
    "capabilities": 8,
    "skills": 8,
    "capability_skills": 9,
    "capability_evidence": 30,
    "initiatives": 5,
    "projects": 8,
    "repositories": 10,
    "sprints": 6,
    "work_items": 30,
    "incidents": 4,
    "deployments": 10,
    "dependencies": 6,
    "ownership": 8,
    "availability": 6,
    "data_sources": 3,
    "ingestion_runs": 4,
    "evidence_signals": 40,
}


def _seed(url: str) -> dict:
    engine = get_engine(url)
    with Session(engine) as session:
        summary = seed_enterprise(session)
        session.commit()
    engine.dispose()
    return summary


def test_first_run_creates_expected_counts(migrated_db):
    summary = _seed(migrated_db)
    for key, expected in EXPECTED_CREATED.items():
        assert summary[key] == expected, f"{key}: {summary[key]} != {expected}"


def test_second_run_creates_zero_duplicates(migrated_db):
    _seed(migrated_db)
    second = _seed(migrated_db)
    assert second["total_created"] == 0
    for key in EXPECTED_CREATED:
        assert second[key] == 0, f"{key} created rows on second run"


def test_row_counts_stable_after_double_seed(migrated_db):
    _seed(migrated_db)
    _seed(migrated_db)
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        org_count = session.scalar(
            select(func.count())
            .select_from(orm.Organization)
            .where(orm.Organization.tenant_id == TENANT_ID)
        )
        evidence_count = session.scalar(
            select(func.count())
            .select_from(orm.EvidenceSignal)
            .where(orm.EvidenceSignal.tenant_id == TENANT_ID)
        )
    engine.dispose()
    assert org_count == 1
    assert evidence_count == 40


def test_deterministic_ids_are_stable(migrated_db):
    _seed(migrated_db)
    engine = get_engine(migrated_db)
    with Session(engine) as session:
        org = session.get(orm.Organization, build_entity_id("org", TENANT_ID, "novabank"))
        assert org is not None
        assert org.name == "NovaBank"
    engine.dispose()


def test_canonical_evidence_hash_is_deterministic():
    payload = {"kind": "commit", "sequence": 0, "repository": "ledger-svc"}
    assert snapshot_hash(payload) == snapshot_hash(dict(reversed(list(payload.items()))))
    assert len(snapshot_hash(payload)) == 64
