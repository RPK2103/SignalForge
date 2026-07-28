"""Phase 2 backward-compatibility projection (Phase 3 Prompt 1).

Projects the immutable Phase 2 catalog (engineers, projects, capabilities) into a
tenant-scoped read view WITHOUT mutating or recomputing any Phase 2 record. This
lets the new tenant boundary intersect legacy data safely: pre-Phase-3 rows were
backfilled to the ``legacy-default`` tenant by the enterprise migration.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import func, select

from app.db.models.catalog import Capability, Engineer, Project
from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import TenantContext


class LegacyEntityRef(BaseModel):
    id: str
    name: str


class LegacyCatalogProjection(BaseModel):
    tenant_id: str
    projects: list[LegacyEntityRef]
    engineers: list[LegacyEntityRef]
    capabilities: list[LegacyEntityRef]
    project_count: int
    engineer_count: int
    capability_count: int


class LegacyCompatibilityService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session

    def project_catalog(self, ctx: TenantContext) -> LegacyCatalogProjection:
        projects = self._session.scalars(
            select(Project).where(Project.tenant_id == ctx.tenant_id).order_by(Project.project_id)
        ).all()
        engineers = self._session.scalars(
            select(Engineer)
            .where(Engineer.tenant_id == ctx.tenant_id)
            .order_by(Engineer.engineer_id)
        ).all()
        capabilities = self._session.scalars(
            select(Capability)
            .where(Capability.tenant_id == ctx.tenant_id)
            .order_by(Capability.capability_id)
        ).all()
        return LegacyCatalogProjection(
            tenant_id=ctx.tenant_id,
            projects=[LegacyEntityRef(id=p.project_id, name=p.name) for p in projects],
            engineers=[LegacyEntityRef(id=e.engineer_id, name=e.name) for e in engineers],
            capabilities=[LegacyEntityRef(id=c.capability_id, name=c.name) for c in capabilities],
            project_count=self._count(Project, ctx),
            engineer_count=self._count(Engineer, ctx),
            capability_count=self._count(Capability, ctx),
        )

    def _count(self, model, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == ctx.tenant_id)
            )
            or 0
        )
