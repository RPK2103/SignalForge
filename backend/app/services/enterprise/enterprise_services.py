"""Focused, tenant-safe enterprise services (Phase 3 Prompt 1).

Each service:
- takes an explicit ``TenantContext``;
- constructs strictly-typed domain DTOs with deterministic, tenant-scoped ids;
- delegates persistence and cross-tenant rejection to tenant-scoped repositories;
- commits through the Unit of Work (rolling back on any error);
- raises domain-specific exceptions and emits structured, secret-free logs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    AvailabilityReason,
    CapabilityCategory,
    Criticality,
    DataSourceStatus,
    DataSourceType,
    DependencyType,
    DeploymentEnvironment,
    DeploymentStatus,
    EmploymentState,
    EngineerLevel,
    EnterpriseEntityType,
    EvidenceSignalType,
    EvidenceStrengthSource,
    IncidentSeverity,
    IncidentState,
    IngestionErrorCategory,
    IngestionRunStatus,
    IngestionRunType,
    InitiativeStatus,
    OrganizationType,
    OwnershipType,
    PermissionClassification,
    ProjectStatus,
    RepositoryVisibility,
    SprintState,
    StrategicPriority,
    TeamType,
    WorkItemPriority,
    WorkItemStatus,
    WorkItemType,
)
from app.domain.enterprise_identifiers import build_entity_id, slugify
from app.domain.tenant_context import TenantContext
from app.security.audit import SecurityAuditService
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission, SecurityAuditAction
from app.services.enterprise.exceptions import (
    EnterpriseConflictError,
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)
from app.services.persistence.snapshot_service import canonical_json, snapshot_hash

_logger = logging.getLogger("signalforge.enterprise")

# Terminal ingestion-run states that can no longer transition.
_TERMINAL_RUN_STATES = {
    IngestionRunStatus.SUCCEEDED,
    IngestionRunStatus.FAILED,
    IngestionRunStatus.PARTIAL,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _BaseService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _commit(self) -> None:
        try:
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise


class EnterpriseHierarchyService(_BaseService):
    def create_organization(
        self,
        ctx: TenantContext,
        *,
        name: str,
        slug: str | None = None,
        organization_type: OrganizationType = OrganizationType.ENTERPRISE,
        timezone_name: str = "UTC",
    ) -> dm.Organization:
        # Enforce the documented cardinality: exactly one organization per tenant.
        if self._uow.organizations.get_tenant_organization(ctx) is not None:
            raise EnterpriseConflictError("This tenant already has an organization")
        org_slug = slugify(slug or name)
        org = dm.Organization(
            organization_id=build_entity_id("org", ctx.tenant_id, org_slug),
            tenant_id=ctx.tenant_id,
            name=name,
            slug=org_slug,
            organization_type=organization_type,
            timezone_name=timezone_name,
        )
        self._uow.organizations.add_organization(ctx, org)
        self._commit()
        _logger.info(
            "enterprise.organization.created tenant_id=%s organization_id=%s",
            ctx.tenant_id,
            org.organization_id,
        )
        return org

    def get_tenant_organization(self, ctx: TenantContext) -> dm.Organization:
        org = self._uow.organizations.get_tenant_organization(ctx)
        if org is None:
            raise EnterpriseNotFoundError("No organization exists for this tenant")
        return org

    def create_business_unit(
        self, ctx: TenantContext, *, organization_id: str, name: str, code: str
    ) -> dm.BusinessUnit:
        bu = dm.BusinessUnit(
            business_unit_id=build_entity_id("bu", ctx.tenant_id, code),
            tenant_id=ctx.tenant_id,
            organization_id=organization_id,
            name=name,
            code=slugify(code),
            valid_from=_utcnow(),
        )
        self._uow.organizations.add_business_unit(ctx, bu)
        self._commit()
        return bu

    def create_department(
        self, ctx: TenantContext, *, business_unit_id: str, name: str, code: str
    ) -> dm.Department:
        dept = dm.Department(
            department_id=build_entity_id("dept", ctx.tenant_id, code),
            tenant_id=ctx.tenant_id,
            business_unit_id=business_unit_id,
            name=name,
            code=slugify(code),
        )
        self._uow.organizations.add_department(ctx, dept)
        self._commit()
        return dept

    def create_team(
        self,
        ctx: TenantContext,
        *,
        department_id: str,
        name: str,
        slug: str | None = None,
        team_type: TeamType = TeamType.PRODUCT,
        capacity_points: int | None = None,
    ) -> dm.Team:
        team_slug = slugify(slug or name)
        team = dm.Team(
            team_id=build_entity_id("team", ctx.tenant_id, team_slug),
            tenant_id=ctx.tenant_id,
            department_id=department_id,
            name=name,
            slug=team_slug,
            team_type=team_type,
            capacity_points=capacity_points,
        )
        self._uow.organizations.add_team(ctx, team)
        self._commit()
        return team

    def list_business_units(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.BusinessUnit]:
        return self._uow.organizations.list_business_units(ctx, limit=limit, offset=offset)

    def list_departments(
        self, ctx: TenantContext, *, limit: int = 50, offset: int = 0
    ) -> dm.Page[dm.Department]:
        return self._uow.organizations.list_departments(ctx, limit=limit, offset=offset)

    def list_teams(
        self, ctx: TenantContext, *, limit: int = 50, offset: int = 0
    ) -> dm.Page[dm.Team]:
        return self._uow.organizations.list_teams(ctx, limit=limit, offset=offset)


class EnterpriseProfileService(_BaseService):
    def create_profile(
        self,
        ctx: TenantContext,
        *,
        display_name: str,
        external_key: str,
        current_team_id: str | None = None,
        role_title: str | None = None,
        level: EngineerLevel | None = None,
        employment_state: EmploymentState = EmploymentState.ACTIVE,
        region: str | None = None,
    ) -> dm.EngineerProfile:
        profile = dm.EngineerProfile(
            engineer_profile_id=build_entity_id("eng", ctx.tenant_id, external_key),
            tenant_id=ctx.tenant_id,
            current_team_id=current_team_id,
            display_name=display_name,
            role_title=role_title,
            level=level,
            employment_state=employment_state,
            region=region,
            valid_from=_utcnow(),
        )
        self._uow.engineer_profiles.add_profile(ctx, profile)
        self._commit()
        return profile

    def get_profile(self, ctx: TenantContext, engineer_profile_id: str) -> dm.EngineerProfile:
        profile = self._uow.engineer_profiles.get_profile(ctx, engineer_profile_id)
        if profile is None:
            raise EnterpriseNotFoundError("Engineer profile not found for this tenant")
        return profile

    def list_profiles(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.EngineerProfile]:
        return self._uow.engineer_profiles.list_profiles(ctx, limit=limit, offset=offset)


class EnterpriseCatalogService(_BaseService):
    def create_capability(
        self,
        ctx: TenantContext,
        *,
        name: str,
        category: CapabilityCategory,
        slug: str | None = None,
        description: str | None = None,
    ) -> dm.EnterpriseCapability:
        cap_slug = slugify(slug or name)
        capability = dm.EnterpriseCapability(
            capability_id=build_entity_id("cap", ctx.tenant_id, cap_slug),
            tenant_id=ctx.tenant_id,
            name=name,
            slug=cap_slug,
            category=category,
            description=description,
        )
        self._uow.enterprise_catalog.add_capability(ctx, capability)
        self._commit()
        return capability

    def create_skill(
        self,
        ctx: TenantContext,
        *,
        name: str,
        category: CapabilityCategory,
        slug: str | None = None,
        description: str | None = None,
    ) -> dm.EnterpriseSkill:
        skill_slug = slugify(slug or name)
        skill = dm.EnterpriseSkill(
            skill_id=build_entity_id("skill", ctx.tenant_id, skill_slug),
            tenant_id=ctx.tenant_id,
            name=name,
            slug=skill_slug,
            category=category,
            description=description,
        )
        self._uow.enterprise_catalog.add_skill(ctx, skill)
        self._commit()
        return skill

    def link_capability_skill(
        self, ctx: TenantContext, *, capability_id: str, skill_id: str
    ) -> dm.CapabilitySkillLink:
        link = dm.CapabilitySkillLink(
            capability_skill_id=build_entity_id("capskill", ctx.tenant_id, capability_id, skill_id),
            tenant_id=ctx.tenant_id,
            capability_id=capability_id,
            skill_id=skill_id,
        )
        self._uow.enterprise_catalog.add_capability_skill(ctx, link)
        self._commit()
        return link

    def add_capability_evidence(
        self,
        ctx: TenantContext,
        *,
        engineer_profile_id: str,
        capability_id: str,
        proficiency: int | None = None,
        source: EvidenceStrengthSource = EvidenceStrengthSource.DECLARED,
        confidence: float = 1.0,
    ) -> dm.EngineerCapabilityEvidence:
        valid_from = _utcnow()
        evidence = dm.EngineerCapabilityEvidence(
            evidence_id=build_entity_id(
                "capev", ctx.tenant_id, engineer_profile_id, capability_id, valid_from.isoformat()
            ),
            tenant_id=ctx.tenant_id,
            engineer_profile_id=engineer_profile_id,
            capability_id=capability_id,
            proficiency=proficiency,
            source=source,
            confidence=confidence,
            valid_from=valid_from,
        )
        self._uow.enterprise_catalog.add_capability_evidence(ctx, evidence)
        self._commit()
        return evidence

    def list_capabilities(
        self, ctx: TenantContext, *, limit: int = 50, offset: int = 0
    ) -> dm.Page[dm.EnterpriseCapability]:
        return self._uow.enterprise_catalog.list_capabilities(ctx, limit=limit, offset=offset)


class InitiativeProjectService(_BaseService):
    def create_initiative(
        self,
        ctx: TenantContext,
        *,
        organization_id: str,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        strategic_priority: StrategicPriority = StrategicPriority.MEDIUM,
        criticality: Criticality = Criticality.MEDIUM,
        status: InitiativeStatus = InitiativeStatus.PROPOSED,
    ) -> dm.Initiative:
        init_slug = slugify(slug or name)
        initiative = dm.Initiative(
            initiative_id=build_entity_id("init", ctx.tenant_id, init_slug),
            tenant_id=ctx.tenant_id,
            organization_id=organization_id,
            name=name,
            slug=init_slug,
            description=description,
            strategic_priority=strategic_priority,
            criticality=criticality,
            status=status,
        )
        self._uow.initiatives_projects.add_initiative(ctx, initiative)
        self._commit()
        return initiative

    def create_project(
        self,
        ctx: TenantContext,
        *,
        name: str,
        slug: str | None = None,
        initiative_id: str | None = None,
        owning_team_id: str | None = None,
        legacy_project_id: str | None = None,
        status: ProjectStatus = ProjectStatus.PLANNED,
        criticality: Criticality = Criticality.MEDIUM,
    ) -> dm.EnterpriseProject:
        project_slug = slugify(slug or name)
        project = dm.EnterpriseProject(
            enterprise_project_id=build_entity_id("proj", ctx.tenant_id, project_slug),
            tenant_id=ctx.tenant_id,
            initiative_id=initiative_id,
            owning_team_id=owning_team_id,
            legacy_project_id=legacy_project_id,
            name=name,
            slug=project_slug,
            status=status,
            criticality=criticality,
        )
        self._uow.initiatives_projects.add_project(ctx, project)
        self._commit()
        return project

    def list_initiatives(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.Initiative]:
        return self._uow.initiatives_projects.list_initiatives(ctx, limit=limit, offset=offset)

    def list_projects(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.EnterpriseProject]:
        return self._uow.initiatives_projects.list_projects(ctx, limit=limit, offset=offset)


class DeliveryService(_BaseService):
    def register_repository(
        self,
        ctx: TenantContext,
        *,
        name: str,
        external_reference: str,
        provider: DataSourceType = DataSourceType.GITHUB,
        owning_team_id: str | None = None,
        default_branch: str | None = "main",
        visibility: RepositoryVisibility = RepositoryVisibility.PRIVATE,
    ) -> dm.Repository:
        repo = dm.Repository(
            repository_id=build_entity_id(
                "repo", ctx.tenant_id, provider.value, external_reference
            ),
            tenant_id=ctx.tenant_id,
            owning_team_id=owning_team_id,
            provider=provider,
            external_reference=external_reference,
            name=name,
            default_branch=default_branch,
            visibility=visibility,
        )
        self._uow.delivery.add_repository(ctx, repo)
        self._commit()
        return repo

    def create_sprint(
        self,
        ctx: TenantContext,
        *,
        team_id: str,
        name: str,
        start_time: datetime,
        end_time: datetime,
        state: SprintState = SprintState.PLANNED,
    ) -> dm.Sprint:
        sprint = dm.Sprint(
            sprint_id=build_entity_id("sprint", ctx.tenant_id, team_id, name),
            tenant_id=ctx.tenant_id,
            team_id=team_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            state=state,
        )
        self._uow.delivery.add_sprint(ctx, sprint)
        self._commit()
        return sprint

    def create_incident(
        self,
        ctx: TenantContext,
        *,
        external_reference: str,
        started_at: datetime,
        severity: IncidentSeverity = IncidentSeverity.SEV3,
        repository_id: str | None = None,
        team_id: str | None = None,
        resolved_at: datetime | None = None,
        state: IncidentState = IncidentState.OPEN,
        provider: DataSourceType = DataSourceType.MANUAL,
    ) -> dm.Incident:
        incident = dm.Incident(
            incident_id=build_entity_id("inc", ctx.tenant_id, provider.value, external_reference),
            tenant_id=ctx.tenant_id,
            repository_id=repository_id,
            team_id=team_id,
            provider=provider,
            external_reference=external_reference,
            severity=severity,
            started_at=started_at,
            resolved_at=resolved_at,
            state=state,
        )
        self._uow.delivery.add_incident(ctx, incident)
        self._commit()
        return incident

    def create_deployment(
        self,
        ctx: TenantContext,
        *,
        external_reference: str,
        started_at: datetime,
        completed_at: datetime | None = None,
        repository_id: str | None = None,
        environment: DeploymentEnvironment = DeploymentEnvironment.PRODUCTION,
        status: DeploymentStatus = DeploymentStatus.SUCCEEDED,
        provider: DataSourceType = DataSourceType.GITHUB,
    ) -> dm.Deployment:
        deployment = dm.Deployment(
            deployment_id=build_entity_id(
                "deploy", ctx.tenant_id, provider.value, external_reference
            ),
            tenant_id=ctx.tenant_id,
            repository_id=repository_id,
            environment=environment,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            provider=provider,
            external_reference=external_reference,
        )
        self._uow.delivery.add_deployment(ctx, deployment)
        self._commit()
        return deployment

    def create_work_item(
        self,
        ctx: TenantContext,
        *,
        external_reference: str,
        provider: DataSourceType = DataSourceType.JIRA,
        enterprise_project_id: str | None = None,
        team_id: str | None = None,
        sprint_id: str | None = None,
        work_item_type: WorkItemType = WorkItemType.STORY,
        status: WorkItemStatus = WorkItemStatus.BACKLOG,
        priority: WorkItemPriority = WorkItemPriority.P2,
    ) -> dm.WorkItem:
        work_item = dm.WorkItem(
            work_item_id=build_entity_id("wi", ctx.tenant_id, provider.value, external_reference),
            tenant_id=ctx.tenant_id,
            enterprise_project_id=enterprise_project_id,
            team_id=team_id,
            sprint_id=sprint_id,
            provider=provider,
            external_reference=external_reference,
            work_item_type=work_item_type,
            status=status,
            priority=priority,
        )
        self._uow.delivery.add_work_item(ctx, work_item)
        self._commit()
        return work_item

    def list_repositories(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.Repository]:
        return self._uow.delivery.list_repositories(ctx, limit=limit, offset=offset)


class RelationshipService(_BaseService):
    def create_dependency(
        self,
        ctx: TenantContext,
        *,
        source_type: EnterpriseEntityType,
        source_id: str,
        target_type: EnterpriseEntityType,
        target_id: str,
        dependency_type: DependencyType,
        criticality: Criticality = Criticality.MEDIUM,
        valid_from: datetime | None = None,
        evidence_reference: str | None = None,
    ) -> dm.Dependency:
        if source_type == target_type and source_id == target_id:
            raise EnterpriseValidationError("A dependency cannot reference itself")
        start = valid_from or _utcnow()
        dependency = dm.Dependency(
            dependency_id=build_entity_id(
                "dep",
                ctx.tenant_id,
                source_type.value,
                source_id,
                target_type.value,
                target_id,
                dependency_type.value,
            ),
            tenant_id=ctx.tenant_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            dependency_type=dependency_type,
            criticality=criticality,
            valid_from=start,
            evidence_reference=evidence_reference,
        )
        self._uow.relationships.add_dependency(ctx, dependency)
        self._commit()
        return dependency

    def create_ownership(
        self,
        ctx: TenantContext,
        *,
        owner_type: EnterpriseEntityType,
        owner_id: str,
        resource_type: EnterpriseEntityType,
        resource_id: str,
        ownership_type: OwnershipType = OwnershipType.PRIMARY,
        allocation: int | None = None,
        valid_from: datetime | None = None,
        evidence_reference: str | None = None,
    ) -> dm.Ownership:
        start = valid_from or _utcnow()
        ownership = dm.Ownership(
            ownership_id=build_entity_id(
                "own",
                ctx.tenant_id,
                owner_type.value,
                owner_id,
                resource_type.value,
                resource_id,
                ownership_type.value,
            ),
            tenant_id=ctx.tenant_id,
            owner_type=owner_type,
            owner_id=owner_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ownership_type=ownership_type,
            allocation=allocation,
            valid_from=start,
            evidence_reference=evidence_reference,
        )
        self._uow.relationships.add_ownership(ctx, ownership)
        self._commit()
        return ownership

    def create_availability(
        self,
        ctx: TenantContext,
        *,
        target_type: EnterpriseEntityType,
        target_id: str,
        start_time: datetime,
        end_time: datetime,
        availability_percentage: int | None = None,
        capacity_units: float | None = None,
        reason: AvailabilityReason = AvailabilityReason.UNKNOWN,
        source: EvidenceStrengthSource = EvidenceStrengthSource.DECLARED,
        confidence: float = 1.0,
    ) -> dm.Availability:
        availability = dm.Availability(
            availability_id=build_entity_id(
                "avail", ctx.tenant_id, target_type.value, target_id, start_time.isoformat()
            ),
            tenant_id=ctx.tenant_id,
            target_type=target_type,
            target_id=target_id,
            availability_percentage=availability_percentage,
            capacity_units=capacity_units,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            source=source,
            confidence=confidence,
        )
        self._uow.relationships.add_availability(ctx, availability)
        self._commit()
        return availability


class IngestionService(_BaseService):
    """Provenance foundation: data sources, ingestion runs and evidence signals.

    NOTE: This performs NO external connector calls. It only records provider-
    neutral provenance and normalized evidence supplied to it.

    Write operations require an authenticated :class:`SecurityContext` and are
    authorized at THIS service boundary (deny-by-default), independently of any
    API-route dependency: data-source configuration requires ``connectors.manage``
    and ingestion execution requires ``connectors.sync``. A direct call without a
    valid context (or with an unauthorized/foreign-tenant context) fails closed.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        super().__init__(uow)
        self._authz = AuthorizationService()
        self._audit = SecurityAuditService(uow)

    def _authorize_write(
        self, context: SecurityContext | None, permission: Permission
    ) -> TenantContext:
        """Deny-by-default service-layer authorization for a write operation.

        Fails closed when ``context`` is absent, is for the wrong tenant, or lacks
        the permission. Returns the tenant-scoped :class:`TenantContext` used for
        persistence only after authorization succeeds.
        """
        self._authz.require_context(context, permission)
        return TenantContext(context.tenant_id)

    def register_data_source(
        self,
        context: SecurityContext,
        *,
        source_type: DataSourceType,
        display_name: str,
        credential_reference: str | None = None,
        config_reference: str | None = None,
        connector_config: dict | None = None,
        permission_classification: PermissionClassification = PermissionClassification.INTERNAL,
        status: DataSourceStatus = DataSourceStatus.REGISTERED,
    ) -> dm.DataSource:
        ctx = self._authorize_write(context, Permission.CONNECTORS_MANAGE)
        from app.connectors.config import hash_connector_config, validate_connector_config
        from app.connectors.credentials import validate_credential_reference

        if credential_reference is not None:
            try:
                validate_credential_reference(credential_reference)
            except Exception as exc:
                from app.connectors.errors import ConnectorError

                if isinstance(exc, ConnectorError):
                    raise EnterpriseValidationError(exc.safe_message) from exc
                raise
        validated_config = None
        config_hash = None
        schema_version = None
        if connector_config is not None:
            try:
                validated_config = validate_connector_config(source_type.value, connector_config)
            except Exception as exc:
                from app.connectors.errors import ConnectorError

                if isinstance(exc, ConnectorError):
                    raise EnterpriseValidationError(exc.safe_message) from exc
                raise
            config_hash = hash_connector_config(validated_config)
            schema_version = "1"
        source = dm.DataSource(
            data_source_id=build_entity_id("ds", ctx.tenant_id, source_type.value, display_name),
            tenant_id=ctx.tenant_id,
            source_type=source_type,
            display_name=display_name,
            credential_reference=credential_reference,
            config_reference=config_reference,
            connector_config=validated_config,
            connector_config_schema_version=schema_version,
            connector_config_hash=config_hash,
            status=status,
            permission_classification=permission_classification,
        )
        self._uow.data_sources.add_data_source(ctx, source)
        self._audit.record_sensitive_action(
            context,
            action=SecurityAuditAction.CONNECTOR_CONFIGURED,
            permission=Permission.CONNECTORS_MANAGE,
            resource_type="data_source",
            resource_id=source.data_source_id,
            metadata={"source_type": source.source_type.value},
        )
        self._commit()
        _logger.info(
            "enterprise.data_source.registered tenant_id=%s data_source_id=%s source_type=%s",
            ctx.tenant_id,
            source.data_source_id,
            source.source_type.value,
        )
        return source

    def start_run(
        self,
        context: SecurityContext,
        *,
        data_source_id: str,
        run_type: IngestionRunType = IngestionRunType.INCREMENTAL,
        run_key: str | None = None,
    ) -> dm.IngestionRun:
        ctx = self._authorize_write(context, Permission.CONNECTORS_SYNC)
        started_at = _utcnow()
        run = dm.IngestionRun(
            ingestion_run_id=build_entity_id(
                "run", ctx.tenant_id, data_source_id, run_key or started_at.isoformat()
            ),
            tenant_id=ctx.tenant_id,
            data_source_id=data_source_id,
            run_type=run_type,
            status=IngestionRunStatus.RUNNING,
            started_at=started_at,
        )
        self._uow.ingestion_runs.add_run(ctx, run)
        self._audit.record_sensitive_action(
            context,
            action=SecurityAuditAction.CONNECTOR_SYNC_INITIATED,
            permission=Permission.CONNECTORS_SYNC,
            resource_type="ingestion_run",
            resource_id=run.ingestion_run_id,
            metadata={"data_source_id": data_source_id, "run_type": run_type.value},
        )
        self._commit()
        _logger.info(
            "enterprise.ingestion_run.started tenant_id=%s ingestion_run_id=%s",
            ctx.tenant_id,
            run.ingestion_run_id,
        )
        return run

    def complete_run(
        self,
        context: SecurityContext,
        *,
        ingestion_run_id: str,
        status: IngestionRunStatus,
        records_read: int = 0,
        records_written: int = 0,
        records_skipped: int = 0,
        error_category: IngestionErrorCategory = IngestionErrorCategory.NONE,
        error_summary: str | None = None,
    ) -> dm.IngestionRun:
        ctx = self._authorize_write(context, Permission.CONNECTORS_SYNC)
        run = self._uow.ingestion_runs.get_run(ctx, ingestion_run_id)
        if run is None:
            raise EnterpriseNotFoundError("Ingestion run not found for this tenant")
        if run.status in _TERMINAL_RUN_STATES:
            raise EnterpriseValidationError(
                f"Ingestion run is already terminal ({run.status.value})"
            )
        if status not in _TERMINAL_RUN_STATES:
            raise EnterpriseValidationError(
                "complete_run requires a terminal status (succeeded/failed/partial)"
            )
        updated = run.model_copy(
            update={
                "status": status,
                "completed_at": _utcnow(),
                "records_read": records_read,
                "records_written": records_written,
                "records_skipped": records_skipped,
                "error_category": error_category,
                "error_summary": _sanitize_error(error_summary),
            }
        )
        result = self._uow.ingestion_runs.update_run(ctx, updated)
        self._audit.record_sensitive_action(
            context,
            action=SecurityAuditAction.CONNECTOR_SYNC_INITIATED,
            permission=Permission.CONNECTORS_SYNC,
            resource_type="ingestion_run",
            resource_id=ingestion_run_id,
            metadata={"status": status.value},
        )
        self._commit()
        _logger.info(
            "enterprise.ingestion_run.completed tenant_id=%s ingestion_run_id=%s status=%s "
            "read=%d written=%d skipped=%d",
            ctx.tenant_id,
            ingestion_run_id,
            status.value,
            records_read,
            records_written,
            records_skipped,
        )
        return result

    def append_evidence(
        self,
        context: SecurityContext,
        *,
        data_source_id: str,
        source_record_id: str,
        signal_type: EvidenceSignalType,
        subject_type: EnterpriseEntityType,
        subject_id: str,
        payload: dict,
        event_time: datetime,
        observed_at: datetime | None = None,
        ingestion_run_id: str | None = None,
        confidence: float = 1.0,
        permission_classification: PermissionClassification = PermissionClassification.INTERNAL,
        expires_at: datetime | None = None,
    ) -> tuple[dm.EvidenceSignal, bool]:
        """Append normalized evidence. Returns ``(signal, created)``; a duplicate
        (same canonical payload hash) is deduplicated rather than overwritten."""
        ctx = self._authorize_write(context, Permission.CONNECTORS_SYNC)
        now = _utcnow()
        observed = observed_at or now
        payload_hash = snapshot_hash(payload)
        provenance = {
            "canonical_payload_length": len(canonical_json(payload)),
            "recorded_by": "signalforge.ingestion_service",
        }
        signal = dm.EvidenceSignal(
            evidence_signal_id=build_entity_id(
                "sig",
                ctx.tenant_id,
                data_source_id,
                source_record_id,
                signal_type.value,
                payload_hash,
            ),
            tenant_id=ctx.tenant_id,
            data_source_id=data_source_id,
            ingestion_run_id=ingestion_run_id,
            source_record_id=source_record_id,
            signal_type=signal_type,
            subject_type=subject_type,
            subject_id=subject_id,
            event_time=event_time,
            observed_at=observed,
            ingested_at=now,
            confidence=confidence,
            permission_classification=permission_classification,
            expires_at=expires_at,
            payload=payload,
            payload_hash=payload_hash,
            provenance=provenance,
        )
        record, created = self._uow.evidence_signals.append(ctx, signal)
        self._commit()
        _logger.info(
            "enterprise.evidence.%s tenant_id=%s evidence_signal_id=%s subject=%s:%s",
            "appended" if created else "deduplicated",
            ctx.tenant_id,
            record.evidence_signal_id,
            subject_type.value,
            subject_id,
        )
        return record, created

    def list_data_sources(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> dm.Page[dm.DataSource]:
        return self._uow.data_sources.list_data_sources(ctx, limit=limit, offset=offset)

    def list_runs(
        self,
        ctx: TenantContext,
        *,
        data_source_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dm.Page[dm.IngestionRun]:
        return self._uow.ingestion_runs.list_runs(
            ctx, data_source_id=data_source_id, limit=limit, offset=offset
        )

    def list_evidence_by_subject(
        self,
        ctx: TenantContext,
        *,
        subject_type: EnterpriseEntityType,
        subject_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.EvidenceSignal]:
        return self._uow.evidence_signals.list_by_subject(
            ctx, subject_type, subject_id, limit=limit, offset=offset
        )


def _sanitize_error(summary: str | None) -> str | None:
    """Best-effort scrub of obvious secret markers from an error summary."""
    if summary is None:
        return None
    redactions = ("password=", "token=", "secret=", "api_key=", "authorization:")
    lowered = summary.lower()
    for marker in redactions:
        if marker in lowered:
            return "[redacted: potential secret in error summary]"
    return summary[:1024]
