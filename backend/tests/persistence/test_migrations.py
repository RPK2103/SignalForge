"""Migration lifecycle tests."""

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command


def test_upgrade_creates_all_tables(migrated_db: str):
    engine = __import__("app.db.session", fromlist=["get_engine"]).get_engine(migrated_db)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "alembic_version",
        "capabilities",
        "engineers",
        "engineer_capabilities",
        "projects",
        "project_requirements",
        "demo_scenarios",
        "assessments",
        "assessment_risk_findings",
        "assessment_decision_traces",
        "simulations",
        "human_reviews",
        "audit_events",
    }
    assert expected.issubset(tables)
    engine.dispose()


def test_single_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1


def test_alembic_check_detects_no_drift(migrated_db: str):
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", migrated_db)
    command.check(cfg)


def test_downgrade_and_reupgrade(migrated_db: str, tmp_path):
    db_path = tmp_path / "downgrade.db"
    url = f"sqlite:///{db_path.as_posix()}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = __import__("app.db.session", fromlist=["get_engine"]).get_engine(url)
    assert "assessments" in inspect(engine).get_table_names()
    engine.dispose()
