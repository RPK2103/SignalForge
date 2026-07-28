"""Tenant-scoped SQL repositories for the enterprise data foundation.

Every method requires an explicit ``TenantContext``. Reads are qualified by
``ctx.tenant_id``; writes stamp and verify ``tenant_id``; associations to parent
entities are validated to belong to the same tenant (cross-tenant references are
rejected). ORM rows never leave this layer — everything is returned as
``app.domain.enterprise_models`` DTOs.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.db.models import enterprise as orm
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import EnterpriseEntityType
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    CrossTenantAccessError,
    EnterpriseConflictError,
    EnterpriseNotFoundError,
)

_MAX_PAGE_SIZE = 100

DTO = TypeVar("DTO", bound=BaseModel)


def _to_dto(dto_cls: type[DTO], row: object) -> DTO:
    return dto_cls.model_validate(row, from_attributes=True)


class _TenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- shared helpers -----------------------------------------------------
    @contextmanager
    def _insert_guard(self, conflict_message: str):
        """Add a row and flush so it is visible to later tenant-scoped lookups
        (autoflush is disabled). A unique/foreign-key violation is mapped to a
        domain :class:`EnterpriseConflictError`.

        NOTE: We deliberately use a plain flush rather than a nested SAVEPOINT.
        Under the pysqlite driver a released SAVEPOINT is committed prematurely,
        which would prevent a later ``rollback()`` from discarding a partial
        multi-step write. On conflict we roll back the active transaction so the
        Unit of Work is left in a clean, reusable state.
        """
        try:
            yield
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise EnterpriseConflictError(conflict_message) from exc

    def _tenant_get(self, model, pk_attr: InstrumentedAttribute, pk: str, ctx: TenantContext):
        return self._session.scalar(
            select(model).where(pk_attr == pk, model.tenant_id == ctx.tenant_id)
        )

    def _require_ref(
        self,
        model,
        pk_attr: InstrumentedAttribute,
        pk: str | None,
        ctx: TenantContext,
        ref_name: str,
    ) -> None:
        """Reject an association whose target is missing or in another tenant."""
        if pk is None:
            return
        row = self._tenant_get(model, pk_attr, pk, ctx)
        if row is None:
            raise CrossTenantAccessError(
                f"Referenced {ref_name} '{pk}' is not visible to this tenant"
            )

    def _paginate(
        self,
        query: Select,
        count_query: Select,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence, int]:
        limit = max(1, min(limit, _MAX_PAGE_SIZE))
        offset = max(0, offset)
        total = self._session.scalar(count_query) or 0
        rows = self._session.scalars(query.offset(offset).limit(limit)).all()
        return rows, total


class OrganizationRepository(_TenantRepository):
    """Organization hierarchy: organizations, business units, departments, teams."""

    def add_organization(self, ctx: TenantContext, org: dm.Organization) -> dm.Organization:
        with self._insert_guard("Organization already exists for this tenant"):
            self._session.add(orm.Organization(**_dump(org, ctx)))
        return org

    def get_organization(self, ctx: TenantContext, organization_id: str) -> dm.Organization | None:
        row = self._tenant_get(
            orm.Organization, orm.Organization.organization_id, organization_id, ctx
        )
        return _to_dto(dm.Organization, row) if row else None

    def get_tenant_organization(self, ctx: TenantContext) -> dm.Organization | None:
        row = self._session.scalar(
            select(orm.Organization).where(orm.Organization.tenant_id == ctx.tenant_id)
        )
        return _to_dto(dm.Organization, row) if row else None

    def add_business_unit(self, ctx: TenantContext, bu: dm.BusinessUnit) -> dm.BusinessUnit:
        self._require_ref(
            orm.Organization,
            orm.Organization.organization_id,
            bu.organization_id,
            ctx,
            "organization",
        )
        with self._insert_guard("Business unit code already exists for this tenant"):
            self._session.add(orm.BusinessUnit(**_dump(bu, ctx)))
        return bu

    def add_department(self, ctx: TenantContext, dept: dm.Department) -> dm.Department:
        self._require_ref(
            orm.BusinessUnit,
            orm.BusinessUnit.business_unit_id,
            dept.business_unit_id,
            ctx,
            "business_unit",
        )
        with self._insert_guard("Department code already exists for this tenant"):
            self._session.add(orm.Department(**_dump(dept, ctx)))
        return dept

    def add_team(self, ctx: TenantContext, team: dm.Team) -> dm.Team:
        self._require_ref(
            orm.Department, orm.Department.department_id, team.department_id, ctx, "department"
        )
        with self._insert_guard("Team slug already exists for this tenant"):
            self._session.add(orm.Team(**_dump(team, ctx)))
        return team

    def get_team(self, ctx: TenantContext, team_id: str) -> dm.Team | None:
        row = self._tenant_get(orm.Team, orm.Team.team_id, team_id, ctx)
        return _to_dto(dm.Team, row) if row else None

    def list_business_units(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.BusinessUnit]:
        base = select(orm.BusinessUnit).where(orm.BusinessUnit.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.BusinessUnit.business_unit_id.asc()),
            select(func.count())
            .select_from(orm.BusinessUnit)
            .where(orm.BusinessUnit.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.BusinessUnit, rows, total, limit, offset)

    def list_departments(
        self, ctx: TenantContext, *, limit: int = 50, offset: int = 0
    ) -> dm.Page[dm.Department]:
        base = select(orm.Department).where(orm.Department.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.Department.department_id.asc()),
            select(func.count())
            .select_from(orm.Department)
            .where(orm.Department.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.Department, rows, total, limit, offset)

    def list_teams(
        self, ctx: TenantContext, *, limit: int = 50, offset: int = 0
    ) -> dm.Page[dm.Team]:
        base = select(orm.Team).where(orm.Team.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.Team.team_id.asc()),
            select(func.count()).select_from(orm.Team).where(orm.Team.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.Team, rows, total, limit, offset)


class EngineerProfileRepository(_TenantRepository):
    def add_profile(self, ctx: TenantContext, profile: dm.EngineerProfile) -> dm.EngineerProfile:
        self._require_ref(orm.Team, orm.Team.team_id, profile.current_team_id, ctx, "team")
        with self._insert_guard("Engineer profile already exists"):
            self._session.add(orm.EngineerProfile(**_dump(profile, ctx)))
        return profile

    def get_profile(
        self, ctx: TenantContext, engineer_profile_id: str
    ) -> dm.EngineerProfile | None:
        row = self._tenant_get(
            orm.EngineerProfile,
            orm.EngineerProfile.engineer_profile_id,
            engineer_profile_id,
            ctx,
        )
        return _to_dto(dm.EngineerProfile, row) if row else None

    def list_profiles(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.EngineerProfile]:
        base = select(orm.EngineerProfile).where(orm.EngineerProfile.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.EngineerProfile.engineer_profile_id.asc()),
            select(func.count())
            .select_from(orm.EngineerProfile)
            .where(orm.EngineerProfile.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.EngineerProfile, rows, total, limit, offset)


class EnterpriseCatalogRepository(_TenantRepository):
    """Capabilities, skills, links and engineer evidence mappings."""

    def add_capability(
        self, ctx: TenantContext, capability: dm.EnterpriseCapability
    ) -> dm.EnterpriseCapability:
        with self._insert_guard("Capability slug already exists for this tenant"):
            self._session.add(orm.EnterpriseCapability(**_dump(capability, ctx)))
        return capability

    def add_skill(self, ctx: TenantContext, skill: dm.EnterpriseSkill) -> dm.EnterpriseSkill:
        with self._insert_guard("Skill slug already exists for this tenant"):
            self._session.add(orm.EnterpriseSkill(**_dump(skill, ctx)))
        return skill

    def add_capability_skill(
        self, ctx: TenantContext, link: dm.CapabilitySkillLink
    ) -> dm.CapabilitySkillLink:
        self._require_ref(
            orm.EnterpriseCapability,
            orm.EnterpriseCapability.capability_id,
            link.capability_id,
            ctx,
            "capability",
        )
        self._require_ref(
            orm.EnterpriseSkill, orm.EnterpriseSkill.skill_id, link.skill_id, ctx, "skill"
        )
        with self._insert_guard("Capability-skill link already exists"):
            self._session.add(orm.CapabilitySkill(**_dump(link, ctx)))
        return link

    def add_capability_evidence(
        self, ctx: TenantContext, evidence: dm.EngineerCapabilityEvidence
    ) -> dm.EngineerCapabilityEvidence:
        self._require_ref(
            orm.EngineerProfile,
            orm.EngineerProfile.engineer_profile_id,
            evidence.engineer_profile_id,
            ctx,
            "engineer_profile",
        )
        self._require_ref(
            orm.EnterpriseCapability,
            orm.EnterpriseCapability.capability_id,
            evidence.capability_id,
            ctx,
            "capability",
        )
        with self._insert_guard("Capability evidence already exists"):
            self._session.add(orm.EngineerCapabilityEvidence(**_dump(evidence, ctx)))
        return evidence

    def add_skill_evidence(
        self, ctx: TenantContext, evidence: dm.EngineerSkillEvidence
    ) -> dm.EngineerSkillEvidence:
        self._require_ref(
            orm.EngineerProfile,
            orm.EngineerProfile.engineer_profile_id,
            evidence.engineer_profile_id,
            ctx,
            "engineer_profile",
        )
        self._require_ref(
            orm.EnterpriseSkill, orm.EnterpriseSkill.skill_id, evidence.skill_id, ctx, "skill"
        )
        with self._insert_guard("Skill evidence already exists"):
            self._session.add(orm.EngineerSkillEvidence(**_dump(evidence, ctx)))
        return evidence

    def list_capabilities(
        self, ctx: TenantContext, *, limit: int = 50, offset: int = 0
    ) -> dm.Page[dm.EnterpriseCapability]:
        base = select(orm.EnterpriseCapability).where(
            orm.EnterpriseCapability.tenant_id == ctx.tenant_id
        )
        rows, total = self._paginate(
            base.order_by(orm.EnterpriseCapability.capability_id.asc()),
            select(func.count())
            .select_from(orm.EnterpriseCapability)
            .where(orm.EnterpriseCapability.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.EnterpriseCapability, rows, total, limit, offset)


class InitiativeProjectRepository(_TenantRepository):
    def add_initiative(self, ctx: TenantContext, initiative: dm.Initiative) -> dm.Initiative:
        self._require_ref(
            orm.Organization,
            orm.Organization.organization_id,
            initiative.organization_id,
            ctx,
            "organization",
        )
        with self._insert_guard("Initiative slug already exists for this tenant"):
            self._session.add(orm.Initiative(**_dump(initiative, ctx)))
        return initiative

    def get_initiative(self, ctx: TenantContext, initiative_id: str) -> dm.Initiative | None:
        row = self._tenant_get(orm.Initiative, orm.Initiative.initiative_id, initiative_id, ctx)
        return _to_dto(dm.Initiative, row) if row else None

    def add_project(
        self, ctx: TenantContext, project: dm.EnterpriseProject
    ) -> dm.EnterpriseProject:
        self._require_ref(
            orm.Initiative, orm.Initiative.initiative_id, project.initiative_id, ctx, "initiative"
        )
        self._require_ref(orm.Team, orm.Team.team_id, project.owning_team_id, ctx, "team")
        with self._insert_guard("Project slug already exists for this tenant"):
            self._session.add(orm.EnterpriseProject(**_dump(project, ctx)))
        return project

    def get_project(
        self, ctx: TenantContext, enterprise_project_id: str
    ) -> dm.EnterpriseProject | None:
        row = self._tenant_get(
            orm.EnterpriseProject,
            orm.EnterpriseProject.enterprise_project_id,
            enterprise_project_id,
            ctx,
        )
        return _to_dto(dm.EnterpriseProject, row) if row else None

    def add_requirement(
        self, ctx: TenantContext, requirement: dm.CapabilityRequirement
    ) -> dm.CapabilityRequirement:
        self._require_ref(
            orm.EnterpriseCapability,
            orm.EnterpriseCapability.capability_id,
            requirement.capability_id,
            ctx,
            "capability",
        )
        with self._insert_guard("Capability requirement already exists"):
            self._session.add(orm.CapabilityRequirement(**_dump(requirement, ctx)))
        return requirement

    def list_initiatives(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.Initiative]:
        base = select(orm.Initiative).where(orm.Initiative.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.Initiative.initiative_id.asc()),
            select(func.count())
            .select_from(orm.Initiative)
            .where(orm.Initiative.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.Initiative, rows, total, limit, offset)

    def list_projects(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.EnterpriseProject]:
        base = select(orm.EnterpriseProject).where(orm.EnterpriseProject.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.EnterpriseProject.enterprise_project_id.asc()),
            select(func.count())
            .select_from(orm.EnterpriseProject)
            .where(orm.EnterpriseProject.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.EnterpriseProject, rows, total, limit, offset)


class DeliveryRepository(_TenantRepository):
    def add_repository(self, ctx: TenantContext, repo: dm.Repository) -> dm.Repository:
        self._require_ref(orm.Team, orm.Team.team_id, repo.owning_team_id, ctx, "team")
        with self._insert_guard("Repository external reference already exists"):
            self._session.add(orm.Repository(**_dump(repo, ctx)))
        return repo

    def get_repository(self, ctx: TenantContext, repository_id: str) -> dm.Repository | None:
        row = self._tenant_get(orm.Repository, orm.Repository.repository_id, repository_id, ctx)
        return _to_dto(dm.Repository, row) if row else None

    def get_repository_by_external(
        self, ctx: TenantContext, *, provider: str, external_reference: str
    ) -> dm.Repository | None:
        row = self._session.scalar(
            select(orm.Repository).where(
                orm.Repository.tenant_id == ctx.tenant_id,
                orm.Repository.provider == provider,
                orm.Repository.external_reference == external_reference,
            )
        )
        return _to_dto(dm.Repository, row) if row else None

    def update_repository(self, ctx: TenantContext, repo: dm.Repository) -> dm.Repository:
        row = self._tenant_get(
            orm.Repository, orm.Repository.repository_id, repo.repository_id, ctx
        )
        if row is None:
            raise EnterpriseNotFoundError("Repository not found for this tenant")
        payload = _dump(repo, ctx)
        for key, value in payload.items():
            if key in {"repository_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.Repository, row)

    def list_repositories(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.Repository]:
        base = select(orm.Repository).where(orm.Repository.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.Repository.repository_id.asc()),
            select(func.count())
            .select_from(orm.Repository)
            .where(orm.Repository.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.Repository, rows, total, limit, offset)

    def add_sprint(self, ctx: TenantContext, sprint: dm.Sprint) -> dm.Sprint:
        self._require_ref(orm.Team, orm.Team.team_id, sprint.team_id, ctx, "team")
        with self._insert_guard("Sprint already exists for team"):
            self._session.add(orm.Sprint(**_dump(sprint, ctx)))
        return sprint

    def add_work_item(self, ctx: TenantContext, work_item: dm.WorkItem) -> dm.WorkItem:
        self._require_ref(
            orm.EnterpriseProject,
            orm.EnterpriseProject.enterprise_project_id,
            work_item.enterprise_project_id,
            ctx,
            "project",
        )
        self._require_ref(orm.Team, orm.Team.team_id, work_item.team_id, ctx, "team")
        self._require_ref(orm.Sprint, orm.Sprint.sprint_id, work_item.sprint_id, ctx, "sprint")
        with self._insert_guard("Work item external reference already exists"):
            self._session.add(orm.WorkItem(**_dump(work_item, ctx)))
        return work_item

    def get_work_item_by_external(
        self, ctx: TenantContext, *, provider: str, external_reference: str
    ) -> dm.WorkItem | None:
        row = self._session.scalar(
            select(orm.WorkItem).where(
                orm.WorkItem.tenant_id == ctx.tenant_id,
                orm.WorkItem.provider == provider,
                orm.WorkItem.external_reference == external_reference,
            )
        )
        return _to_dto(dm.WorkItem, row) if row else None

    def update_work_item(self, ctx: TenantContext, work_item: dm.WorkItem) -> dm.WorkItem:
        row = self._tenant_get(orm.WorkItem, orm.WorkItem.work_item_id, work_item.work_item_id, ctx)
        if row is None:
            raise EnterpriseNotFoundError("Work item not found for this tenant")
        payload = _dump(work_item, ctx)
        for key, value in payload.items():
            if key in {"work_item_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.WorkItem, row)

    def add_incident(self, ctx: TenantContext, incident: dm.Incident) -> dm.Incident:
        self._require_ref(
            orm.Repository, orm.Repository.repository_id, incident.repository_id, ctx, "repository"
        )
        self._require_ref(orm.Team, orm.Team.team_id, incident.team_id, ctx, "team")
        with self._insert_guard("Incident external reference already exists"):
            self._session.add(orm.Incident(**_dump(incident, ctx)))
        return incident

    def add_deployment(self, ctx: TenantContext, deployment: dm.Deployment) -> dm.Deployment:
        self._require_ref(
            orm.Repository,
            orm.Repository.repository_id,
            deployment.repository_id,
            ctx,
            "repository",
        )
        with self._insert_guard("Deployment external reference already exists"):
            self._session.add(orm.Deployment(**_dump(deployment, ctx)))
        return deployment


class RelationshipRepository(_TenantRepository):
    def add_dependency(self, ctx: TenantContext, dependency: dm.Dependency) -> dm.Dependency:
        with self._insert_guard("Dependency edge already exists"):
            self._session.add(orm.Dependency(**_dump(dependency, ctx)))
        return dependency

    def add_ownership(self, ctx: TenantContext, ownership: dm.Ownership) -> dm.Ownership:
        with self._insert_guard("Ownership edge already exists"):
            self._session.add(orm.Ownership(**_dump(ownership, ctx)))
        return ownership

    def add_availability(
        self, ctx: TenantContext, availability: dm.Availability
    ) -> dm.Availability:
        with self._insert_guard("Availability window already exists"):
            self._session.add(orm.Availability(**_dump(availability, ctx)))
        return availability

    def list_dependencies(
        self,
        ctx: TenantContext,
        *,
        source_type: EnterpriseEntityType | None = None,
        source_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.Dependency]:
        base = select(orm.Dependency).where(orm.Dependency.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.Dependency)
            .where(orm.Dependency.tenant_id == ctx.tenant_id)
        )
        if source_type is not None:
            base = base.where(orm.Dependency.source_type == source_type.value)
            count = count.where(orm.Dependency.source_type == source_type.value)
        if source_id is not None:
            base = base.where(orm.Dependency.source_id == source_id)
            count = count.where(orm.Dependency.source_id == source_id)
        rows, total = self._paginate(
            base.order_by(orm.Dependency.dependency_id.asc()), count, limit=limit, offset=offset
        )
        return _page(dm.Dependency, rows, total, limit, offset)


class DataSourceRepository(_TenantRepository):
    def add_data_source(self, ctx: TenantContext, source: dm.DataSource) -> dm.DataSource:
        with self._insert_guard("Data source already exists for this tenant"):
            self._session.add(orm.DataSource(**_dump(source, ctx)))
        return source

    def get_data_source(self, ctx: TenantContext, data_source_id: str) -> dm.DataSource | None:
        row = self._tenant_get(orm.DataSource, orm.DataSource.data_source_id, data_source_id, ctx)
        return _to_dto(dm.DataSource, row) if row else None

    def update_data_source(self, ctx: TenantContext, source: dm.DataSource) -> dm.DataSource:
        row = self._tenant_get(
            orm.DataSource, orm.DataSource.data_source_id, source.data_source_id, ctx
        )
        if row is None:
            raise EnterpriseNotFoundError(
                f"Data source '{source.data_source_id}' not found for tenant"
            )
        payload = _dump(source, ctx)
        for key, value in payload.items():
            if key in {"data_source_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.DataSource, row)

    def list_data_sources(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.DataSource]:
        base = select(orm.DataSource).where(orm.DataSource.tenant_id == ctx.tenant_id)
        rows, total = self._paginate(
            base.order_by(orm.DataSource.data_source_id.asc()),
            select(func.count())
            .select_from(orm.DataSource)
            .where(orm.DataSource.tenant_id == ctx.tenant_id),
            limit=limit,
            offset=offset,
        )
        return _page(dm.DataSource, rows, total, limit, offset)


class IngestionRunRepository(_TenantRepository):
    def add_run(self, ctx: TenantContext, run: dm.IngestionRun) -> dm.IngestionRun:
        self._require_ref(
            orm.DataSource, orm.DataSource.data_source_id, run.data_source_id, ctx, "data_source"
        )
        with self._insert_guard("Ingestion run already exists"):
            self._session.add(orm.IngestionRun(**_dump(run, ctx)))
        return run

    def get_run(self, ctx: TenantContext, ingestion_run_id: str) -> dm.IngestionRun | None:
        row = self._tenant_get(
            orm.IngestionRun, orm.IngestionRun.ingestion_run_id, ingestion_run_id, ctx
        )
        return _to_dto(dm.IngestionRun, row) if row else None

    def update_run(self, ctx: TenantContext, run: dm.IngestionRun) -> dm.IngestionRun:
        row = self._tenant_get(
            orm.IngestionRun, orm.IngestionRun.ingestion_run_id, run.ingestion_run_id, ctx
        )
        if row is None:
            raise EnterpriseNotFoundError(
                f"Ingestion run '{run.ingestion_run_id}' not found for tenant"
            )
        payload = _dump(run, ctx)
        for key, value in payload.items():
            if key in {"ingestion_run_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.IngestionRun, row)

    def list_runs(
        self,
        ctx: TenantContext,
        *,
        data_source_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dm.Page[dm.IngestionRun]:
        base = select(orm.IngestionRun).where(orm.IngestionRun.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.IngestionRun)
            .where(orm.IngestionRun.tenant_id == ctx.tenant_id)
        )
        if data_source_id is not None:
            base = base.where(orm.IngestionRun.data_source_id == data_source_id)
            count = count.where(orm.IngestionRun.data_source_id == data_source_id)
        rows, total = self._paginate(
            base.order_by(orm.IngestionRun.ingestion_run_id.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.IngestionRun, rows, total, limit, offset)


class EvidenceSignalRepository(_TenantRepository):
    """Append-only evidence store with deterministic deduplication."""

    def _find_duplicate(self, ctx: TenantContext, signal: dm.EvidenceSignal):
        return self._session.scalar(
            select(orm.EvidenceSignal).where(
                orm.EvidenceSignal.tenant_id == ctx.tenant_id,
                orm.EvidenceSignal.data_source_id == signal.data_source_id,
                orm.EvidenceSignal.source_record_id == signal.source_record_id,
                orm.EvidenceSignal.signal_type == signal.signal_type.value,
                orm.EvidenceSignal.payload_hash == signal.payload_hash,
            )
        )

    def append(
        self, ctx: TenantContext, signal: dm.EvidenceSignal
    ) -> tuple[dm.EvidenceSignal, bool]:
        """Append a signal. Returns ``(record, created)``.

        Idempotent: an identical (tenant, source, source_record, type, hash)
        signal is never duplicated; the existing record is returned instead.
        """
        self._require_ref(
            orm.DataSource, orm.DataSource.data_source_id, signal.data_source_id, ctx, "data_source"
        )
        if signal.ingestion_run_id is not None:
            self._require_ref(
                orm.IngestionRun,
                orm.IngestionRun.ingestion_run_id,
                signal.ingestion_run_id,
                ctx,
                "ingestion_run",
            )
        existing = self._find_duplicate(ctx, signal)
        if existing is not None:
            return _to_dto(dm.EvidenceSignal, existing), False
        try:
            self._session.add(orm.EvidenceSignal(**_dump(signal, ctx)))
            self._session.flush()
        except IntegrityError:
            # Lost a dedup race: another writer committed the same canonical
            # signal first. Roll back our failed insert and return theirs.
            self._session.rollback()
            existing = self._find_duplicate(ctx, signal)
            if existing is not None:
                return _to_dto(dm.EvidenceSignal, existing), False
            raise
        return signal, True

    def get(self, ctx: TenantContext, evidence_signal_id: str) -> dm.EvidenceSignal | None:
        row = self._tenant_get(
            orm.EvidenceSignal,
            orm.EvidenceSignal.evidence_signal_id,
            evidence_signal_id,
            ctx,
        )
        return _to_dto(dm.EvidenceSignal, row) if row else None

    def list_by_subject(
        self,
        ctx: TenantContext,
        subject_type: EnterpriseEntityType,
        subject_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.EvidenceSignal]:
        base = select(orm.EvidenceSignal).where(
            orm.EvidenceSignal.tenant_id == ctx.tenant_id,
            orm.EvidenceSignal.subject_type == subject_type.value,
            orm.EvidenceSignal.subject_id == subject_id,
        )
        count = (
            select(func.count())
            .select_from(orm.EvidenceSignal)
            .where(
                orm.EvidenceSignal.tenant_id == ctx.tenant_id,
                orm.EvidenceSignal.subject_type == subject_type.value,
                orm.EvidenceSignal.subject_id == subject_id,
            )
        )
        rows, total = self._paginate(
            base.order_by(orm.EvidenceSignal.evidence_signal_id.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.EvidenceSignal, rows, total, limit, offset)

    def list_by_source(
        self,
        ctx: TenantContext,
        data_source_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.EvidenceSignal]:
        base = select(orm.EvidenceSignal).where(
            orm.EvidenceSignal.tenant_id == ctx.tenant_id,
            orm.EvidenceSignal.data_source_id == data_source_id,
        )
        count = (
            select(func.count())
            .select_from(orm.EvidenceSignal)
            .where(
                orm.EvidenceSignal.tenant_id == ctx.tenant_id,
                orm.EvidenceSignal.data_source_id == data_source_id,
            )
        )
        rows, total = self._paginate(
            base.order_by(orm.EvidenceSignal.evidence_signal_id.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.EvidenceSignal, rows, total, limit, offset)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dump(model: BaseModel, ctx: TenantContext) -> dict:
    """Serialize a domain DTO to ORM column kwargs, forcing the tenant boundary.

    Enum values are unwrapped to their string values; the caller's tenant always
    wins so a DTO can never smuggle a different tenant into a write.
    """
    data = model.model_dump()
    data["tenant_id"] = ctx.tenant_id
    for key, value in list(data.items()):
        if hasattr(value, "value"):
            data[key] = value.value
    # Timestamps are managed by ORM defaults; drop Nones so defaults apply.
    for ts_key in ("created_at", "updated_at"):
        if ts_key in data and data[ts_key] is None:
            data.pop(ts_key)
    return data


def _page(dto_cls: type[DTO], rows: Sequence, total: int, limit: int, offset: int) -> dm.Page:
    normalized_limit = max(1, min(limit, _MAX_PAGE_SIZE))
    return dm.Page[dto_cls](
        items=[_to_dto(dto_cls, row) for row in rows],
        total=total,
        limit=normalized_limit,
        offset=max(0, offset),
    )
