"""Migration tests: heads, up/down/re-up, Phase 2 backfill, constraints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import enterprise as orm
from app.db.session import reset_engine

PHASE_2_HEAD = "a1b2c3d4e5f6"
P3_DELIVERY_GRAPH = "p3_delivery_graph"
P3_DELIVERY_PREDICTION = "p3_delivery_prediction"
P3_CONTINUOUS_SCENARIO_INTELLIGENCE = "p3_continuous_scenario_intelligence"
P3_AI_CHIEF_OF_STAFF = "p3_ai_chief_of_staff"
P3_ENTERPRISE_SECURITY_SCALE = "p3_enterprise_security_scale"
P3_OBSERVABILITY_AI_QUALITY = "p3_observability_ai_quality"
CURRENT_ALEMBIC_HEAD = P3_OBSERVABILITY_AI_QUALITY
P3_PROMPT1 = "p3_enterprise_foundation"
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _alembic_config():
    from alembic.config import Config

    return Config("alembic.ini")


def _upgrade(url: str, revision: str) -> None:
    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    command.upgrade(_alembic_config(), revision)


def _downgrade(url: str, revision: str) -> None:
    from alembic import command

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()
    command.downgrade(_alembic_config(), revision)


@pytest.fixture
def temp_url(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    yield url
    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


def test_exactly_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert heads == [CURRENT_ALEMBIC_HEAD]


def test_upgrade_downgrade_reupgrade(temp_url: str):
    _upgrade(temp_url, "head")
    engine = create_engine(temp_url)
    assert "ent_organizations" in inspect(engine).get_table_names()
    engine.dispose()

    _downgrade(temp_url, PHASE_2_HEAD)
    engine = create_engine(temp_url)
    tables = inspect(engine).get_table_names()
    assert "ent_organizations" not in tables
    assert "projects" in tables  # Phase 2 tables survive downgrade
    engine.dispose()

    _upgrade(temp_url, "head")
    engine = create_engine(temp_url)
    assert "ent_evidence_signals" in inspect(engine).get_table_names()
    assert "ent_connector_checkpoints" in inspect(engine).get_table_names()
    engine.dispose()


def test_phase2_rows_backfilled_to_legacy_tenant(temp_url: str):
    _upgrade(temp_url, PHASE_2_HEAD)
    engine = create_engine(temp_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO capabilities "
                "(capability_id, name, category, schema_version, created_at, updated_at) "
                "VALUES ('legacy_cap', 'Legacy Cap', 'backend', '1', :now, :now)"
            ),
            {"now": _NOW},
        )
        conn.execute(
            text(
                "INSERT INTO engineers "
                "(engineer_id, name, experience_years, has_certifications, "
                "has_project_history, schema_version, created_at, updated_at) "
                "VALUES ('legacy_eng', 'Legacy Eng', 5, 1, 1, '1', :now, :now)"
            ),
            {"now": _NOW},
        )
        conn.execute(
            text(
                "INSERT INTO projects "
                "(project_id, name, schema_version, created_at, updated_at) "
                "VALUES ('legacy_proj', 'Legacy Proj', '1', :now, :now)"
            ),
            {"now": _NOW},
        )
    engine.dispose()

    _upgrade(temp_url, "head")

    engine = create_engine(temp_url)
    with engine.connect() as conn:
        for table, pk_col, pk in (
            ("capabilities", "capability_id", "legacy_cap"),
            ("engineers", "engineer_id", "legacy_eng"),
            ("projects", "project_id", "legacy_proj"),
        ):
            tenant = conn.execute(
                text(f"SELECT tenant_id FROM {table} WHERE {pk_col} = :pk"), {"pk": pk}
            ).scalar()
            assert tenant == "legacy-default", f"{table} not backfilled"
    engine.dispose()


def test_evidence_indexes_and_unique_constraints_present(temp_url: str):
    _upgrade(temp_url, "head")
    engine = create_engine(temp_url)
    insp = inspect(engine)

    index_names = {ix["name"] for ix in insp.get_indexes("ent_evidence_signals")}
    assert "ix_ent_evidence_signals_subject" in index_names
    assert "ix_ent_evidence_signals_tenant_id" in index_names

    unique_names = {uc["name"] for uc in insp.get_unique_constraints("ent_evidence_signals")}
    assert "uq_ent_evidence_signals_dedup" in unique_names

    org_indexes = {ix["name"] for ix in insp.get_indexes("ent_organizations")}
    assert "ix_ent_organizations_tenant_id" in org_indexes
    engine.dispose()


def test_tenant_scoped_uniqueness(temp_url: str):
    _upgrade(temp_url, "head")
    engine = create_engine(temp_url)
    # Same org slug is allowed across tenants but only one org per tenant.
    with Session(engine) as session:
        session.add(
            orm.Organization(
                organization_id="o_a",
                tenant_id="tenant-a",
                name="Nova",
                slug="nova",
                organization_type="enterprise",
                timezone_name="UTC",
                schema_version="1",
            )
        )
        session.add(
            orm.Organization(
                organization_id="o_b",
                tenant_id="tenant-b",
                name="Nova",
                slug="nova",
                organization_type="enterprise",
                timezone_name="UTC",
                schema_version="1",
            )
        )
        session.commit()

    with Session(engine) as session:
        session.add(
            orm.Organization(
                organization_id="o_a2",
                tenant_id="tenant-a",
                name="Second",
                slug="second",
                organization_type="enterprise",
                timezone_name="UTC",
                schema_version="1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()  # one organization per tenant
    engine.dispose()
