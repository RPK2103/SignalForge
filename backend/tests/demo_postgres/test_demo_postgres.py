"""PostgreSQL coverage for Prompt 9 NovaBank demo materialization.

When POSTGRES_TEST_URL is unset, a non-skipped marker test still collects so
CI can detect an empty suite. When set, the live suite seeds, materializes
(including Delivery Graph rebuild), validates the eight-story matrix, and
rebuilds the graph a second time for idempotency on PostgreSQL 16.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo.novabank.constants import DATASET_VERSION, SCHEMA_COMPAT, TENANT_ID


def test_prompt9_uses_existing_schema_compat():
    assert SCHEMA_COMPAT == "p3_observability_ai_quality"
    assert DATASET_VERSION.startswith("novabank-enterprise-demo")


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_TEST_URL"),
    reason="POSTGRES_TEST_URL not set — remote CI runs this suite on Postgres 16",
)
def test_postgres_canonical_seed_materialize_graph_rebuild():
    from app.core.config import get_settings
    from app.db.models import graph as graph_orm
    from app.db.session import get_engine, init_engine, reset_engine
    from app.db.unit_of_work import UnitOfWork
    from app.demo.novabank.service import NovaBankDemoService
    from app.demo.novabank.validation import validate_dataset
    from app.domain.tenant_context import TenantContext
    from app.security.context import internal_system_context
    from app.security.enums import SecurityRole
    from app.security.permissions import permissions_for_roles
    from app.services.graph.projection_service import GraphProjectionService

    url = os.environ["POSTGRES_TEST_URL"]
    get_settings.cache_clear()
    reset_engine()
    init_engine(url)
    engine = get_engine(url)
    session = Session(engine)
    try:
        security = internal_system_context(
            TENANT_ID,
            correlation_id="pg-demo-p9",
            roles=frozenset({SecurityRole.TENANT_ADMIN}),
            permissions=permissions_for_roles(frozenset({SecurityRole.TENANT_ADMIN})),
        )
        service = NovaBankDemoService(session, security)
        seed = service.seed()
        assert seed["manifest_hash"]
        mat = service.materialize()
        assert mat["ok"] is True
        assert mat["graph_rebuilt"] is True
        assert mat["scenarios_executed"] == 8
        assert mat["briefs_generated"] == 8

        report = validate_dataset(session)
        assert report.ok, report.errors
        assert len(report.story_matrix) == 8
        for row in report.story_matrix:
            for key in (
                "target",
                "evidence",
                "graph",
                "prediction_or_fallback",
                "scenario",
                "brief",
                "citations",
            ):
                assert row[key], row

        ctx = TenantContext.require(TENANT_ID)
        uow = UnitOfWork(session)
        edges_1 = session.scalar(
            select(func.count())
            .select_from(graph_orm.DeliveryGraphEdge)
            .where(
                graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
                graph_orm.DeliveryGraphEdge.archived_at.is_(None),
            )
        )
        GraphProjectionService(uow).full_rebuild(ctx)
        session.commit()
        edges_2 = session.scalar(
            select(func.count())
            .select_from(graph_orm.DeliveryGraphEdge)
            .where(
                graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
                graph_orm.DeliveryGraphEdge.archived_at.is_(None),
            )
        )
        assert edges_1 == edges_2
        assert edges_1 and edges_1 > 0
        bad = session.scalar(
            select(func.count())
            .select_from(graph_orm.DeliveryGraphEdge)
            .where(
                graph_orm.DeliveryGraphEdge.tenant_id == TENANT_ID,
                graph_orm.DeliveryGraphEdge.valid_to.is_not(None),
                graph_orm.DeliveryGraphEdge.valid_to <= graph_orm.DeliveryGraphEdge.valid_from,
            )
        )
        assert bad == 0
    finally:
        session.close()
        engine.dispose()
        reset_engine()
        get_settings.cache_clear()
