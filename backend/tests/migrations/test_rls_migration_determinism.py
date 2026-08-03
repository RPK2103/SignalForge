"""Historical RLS migration determinism (Phase 3 Prompt 8 CI remediation).

Prompt 7 must use a frozen revision-local table snapshot so a later Prompt 8
ORM registration cannot make Prompt 7 ALTER tables that do not yet exist.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
from pathlib import Path
from types import ModuleType

from alembic.config import Config
from alembic.script import ScriptDirectory

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

PROMPT8_TABLES = frozenset(
    {
        "ent_observability_metric_rollups",
        "ent_slo_definitions",
        "ent_slo_evaluations",
        "ent_alert_events",
        "ent_ai_evaluation_datasets",
        "ent_ai_evaluation_cases",
        "ent_ai_evaluation_runs",
        "ent_ai_evaluation_results",
        "ent_prediction_quality_snapshots",
    }
)


def _load_migration(stem: str) -> ModuleType:
    path = VERSIONS_DIR / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"signalforge_mig_{stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt7_snapshot_excludes_all_prompt8_tables():
    p7 = _load_migration("p3_enterprise_security_scale")
    snapshot = set(p7.PROMPT7_RLS_TABLES)
    assert snapshot.isdisjoint(PROMPT8_TABLES)
    assert "ent_ai_evaluation_datasets" not in snapshot


def test_prompt8_snapshot_contains_exactly_nine_tables():
    p8 = _load_migration("p3_observability_ai_quality")
    assert len(p8.PROMPT8_RLS_TABLES) == 9
    assert set(p8.PROMPT8_RLS_TABLES) == PROMPT8_TABLES


def test_prompt7_snapshot_immune_to_runtime_registry_growth(monkeypatch):
    """Mutating the evolving runtime registry must not change Prompt 7's list."""
    from app.db import models as _models  # noqa: F401
    from app.db.base import Base
    from app.security import rls as rls_mod

    p7 = _load_migration("p3_enterprise_security_scale")
    before = tuple(p7.PROMPT7_RLS_TABLES)
    real_tables = rls_mod.tenant_rls_tables(Base.metadata)

    def inflated(_metadata):
        return [*real_tables, "ent_future_fake_table_xyz"]

    monkeypatch.setattr(rls_mod, "tenant_rls_tables", inflated)
    assert tuple(p7.PROMPT7_RLS_TABLES) == before
    assert "ent_future_fake_table_xyz" not in p7.PROMPT7_RLS_TABLES
    assert "ent_ai_evaluation_datasets" not in p7.PROMPT7_RLS_TABLES
    # Runtime registry (even when inflated) may include Prompt 8 tables.
    assert "ent_ai_evaluation_datasets" in inflated(Base.metadata)


def test_prompt7_upgrade_does_not_call_tenant_rls_tables():
    p7 = _load_migration("p3_enterprise_security_scale")
    source = inspect.getsource(p7.upgrade)
    assert "tenant_rls_tables" not in source
    assert "PROMPT7_RLS_TABLES" in source
    assert "Base.metadata" not in source


def test_prompt8_rls_runs_only_after_table_creation():
    """Behavioral ordering: every Prompt 8 create_table precedes RLS enablement."""
    path = VERSIONS_DIR / "p3_observability_ai_quality.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    upgrade_fn = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )

    create_tables: list[str] = []
    create_linenos: list[int] = []
    rls_loop_lineno: int | None = None
    for node in ast.walk(upgrade_fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            create_tables.append(node.args[0].value)
            create_linenos.append(node.lineno)
        if isinstance(node, ast.For) and "PROMPT8_RLS_TABLES" in ast.unparse(node.iter):
            rls_loop_lineno = node.lineno

    assert set(create_tables) == PROMPT8_TABLES
    assert rls_loop_lineno is not None
    assert create_linenos
    assert max(create_linenos) < rls_loop_lineno


def test_runtime_registry_includes_prompt8_without_changing_prompt7():
    from app.db import models as _models  # noqa: F401
    from app.db.base import Base
    from app.security.rls import tenant_rls_tables

    p7 = _load_migration("p3_enterprise_security_scale")
    runtime = set(tenant_rls_tables(Base.metadata))
    assert PROMPT8_TABLES.issubset(runtime)
    assert set(p7.PROMPT7_RLS_TABLES).isdisjoint(PROMPT8_TABLES)


def test_single_alembic_head_remains_observability():
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["p3_observability_ai_quality"]


def test_downgrade_reupgrade_prompt8_head(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect

    from alembic import command
    from app.core.config import get_settings
    from app.db.session import reset_engine

    url = f"sqlite:///{(tmp_path / 'rls_det.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    reset_engine()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "p3_enterprise_security_scale")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert PROMPT8_TABLES.issubset(tables)
    reset_engine()
    get_settings.cache_clear()
