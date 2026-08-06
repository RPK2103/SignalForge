"""Specification, determinism and inventory tests for NovaBank Prompt 9."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.demo.novabank.constants import AS_OF_AT, DATASET_VERSION, GENERATOR_VERSION
from app.demo.novabank.manifest import build_manifest
from app.demo.novabank.service import NovaBankDemoService
from app.demo.novabank.specification import CANONICAL_SPEC, TARGET_INVENTORY, DatasetSpecification
from app.demo.novabank.validation import validate_dataset
from app.security.exceptions import AuthorizationError


def test_canonical_spec_valid():
    CANONICAL_SPEC.validate()
    assert CANONICAL_SPEC.dataset_version == DATASET_VERSION
    assert CANONICAL_SPEC.generator_version == GENERATOR_VERSION
    assert CANONICAL_SPEC.as_of_at == AS_OF_AT
    assert len(CANONICAL_SPEC.stories) == 8
    assert CANONICAL_SPEC.production_ineligible is True


def test_story_ids_unique_and_sorted():
    ids = [s.story_id for s in CANONICAL_SPEC.stories]
    assert ids == sorted(ids)
    assert len(set(ids)) == 8


def test_target_inventory_ranges():
    assert TARGET_INVENTORY["engineers"] == 48
    assert TARGET_INVENTORY["business_units"] == 5
    assert TARGET_INVENTORY["teams"] == 10
    assert TARGET_INVENTORY["initiatives"] == 14
    assert TARGET_INVENTORY["repositories"] == 32
    assert TARGET_INVENTORY["work_items"] == 480
    assert TARGET_INVENTORY["pull_requests"] == 220


def test_as_of_must_match_constant():
    with pytest.raises(ValueError):
        DatasetSpecification(
            dataset_name=CANONICAL_SPEC.dataset_name,
            dataset_version=CANONICAL_SPEC.dataset_version,
            generator_version=CANONICAL_SPEC.generator_version,
            schema_compat=CANONICAL_SPEC.schema_compat,
            as_of_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            target_inventory=dict(TARGET_INVENTORY),
            stories=CANONICAL_SPEC.stories,
        ).validate()


def test_seed_requires_security(demo_session: Session):
    with pytest.raises(AuthorizationError):
        NovaBankDemoService(demo_session, None)  # type: ignore[arg-type]


def test_seed_denies_reader_role(demo_session: Session, reader_security):
    service = NovaBankDemoService(demo_session, reader_security)
    with pytest.raises(AuthorizationError):
        service.seed()


def test_first_seed_reaches_inventory(seeded_demo: dict, demo_session: Session, demo_security):
    assert seeded_demo["created_total"] > 0
    assert seeded_demo["manifest_hash"]
    report = NovaBankDemoService(demo_session, demo_security).validate()
    assert report.inventory["organizations"] == 1
    assert report.inventory["business_units"] == 5
    assert report.inventory["teams"] == 10
    assert report.inventory["engineers"] == 48
    assert report.inventory["initiatives"] == 14
    assert report.inventory["projects"] == 24
    assert report.inventory["repositories"] == 32
    assert report.inventory["sprints"] == 30
    assert report.inventory["work_items"] == 480
    assert report.inventory["pull_requests"] == 220
    assert report.inventory["deployments"] == 75
    assert report.inventory["incidents"] == 32
    assert report.inventory["dependencies"] == 58
    assert report.inventory["ownership"] == 120
    assert report.inventory["availability"] == 18
    assert report.ok, report.errors


def test_second_seed_idempotent(demo_session: Session, demo_security, seeded_demo: dict):
    first_hash = seeded_demo["manifest_hash"]
    second = NovaBankDemoService(demo_session, demo_security).seed()
    assert second["manifest_hash"] == first_hash
    # Canonical entity categories should create zero new rows.
    for key in (
        "organizations",
        "business_units",
        "teams",
        "engineers",
        "initiatives",
        "projects",
        "repositories",
        "work_items",
        "pull_requests",
        "deployments",
        "incidents",
        "dependencies",
        "ownership",
        "availability",
    ):
        assert second["created"][key] == 0, key


def test_manifest_stable_across_databases(tmp_path, demo_security):
    from app.core.config import get_settings
    from app.db.session import get_engine, init_engine, reset_engine
    from tests.demo.conftest import _run_alembic

    hashes = []
    for name in ("a.db", "b.db"):
        url = f"sqlite:///{(tmp_path / name).as_posix()}"
        _run_alembic(url)
        reset_engine()
        init_engine(url)
        engine = get_engine(url)
        with Session(engine) as session:
            result = NovaBankDemoService(session, demo_security).seed()
            hashes.append(result["manifest_hash"])
            rebuilt = build_manifest(session)["manifest_hash"]
            assert rebuilt == result["manifest_hash"]
        engine.dispose()
        reset_engine()
        get_settings.cache_clear()
    assert hashes[0] == hashes[1]


def test_no_sensitive_engineer_fields(seeded_demo, demo_session: Session):
    report = validate_dataset(demo_session)
    assert not any("sensitive field" in e for e in report.errors)


def test_stories_have_scenarios(seeded_demo, demo_session: Session):
    report = validate_dataset(demo_session)
    for row in report.story_matrix:
        assert row["target"] is True
        assert row["scenario"] is True
