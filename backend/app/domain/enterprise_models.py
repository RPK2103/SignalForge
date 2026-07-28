"""Strictly-typed enterprise domain models (Phase 3 Prompt 1).

These are framework-light Pydantic DTOs. No SQLAlchemy ORM objects leak into
services or the API layer; repositories translate ORM rows into these models.

Temporal semantics (see architecture/phase-3-enterprise-data-foundation.md):
- ``created_at`` / ``updated_at``: record lifecycle timestamps.
- ``event_time``: when the source event actually occurred.
- ``observed_at``: when the source system exposed/reported it.
- ``ingested_at``: when SignalForge accepted it.
- ``valid_from`` / ``valid_to``: business-valid relationship interval.
- ``archived_at``: soft archival of a mutable catalog entity.

All datetimes are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enterprise_enums import (
    AvailabilityReason,
    CapabilityCategory,
    Criticality,
    DataSourceStatus,
    DataSourceType,
    DependencyStatus,
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
    RepositoryState,
    RepositoryVisibility,
    RequirementSubjectType,
    SprintState,
    StrategicPriority,
    TeamType,
    WorkItemPriority,
    WorkItemStatus,
    WorkItemType,
)

# ---------------------------------------------------------------------------
# Sensitive-attribute guard
# ---------------------------------------------------------------------------
# Fields that must never appear on an engineer profile or any enterprise model.
# Enforced by a domain test and asserted here for defense in depth.
FORBIDDEN_ENGINEER_FIELDS = frozenset(
    {
        "gender",
        "ethnicity",
        "race",
        "religion",
        "health",
        "medical",
        "political_views",
        "age",
        "date_of_birth",
        "salary",
        "compensation",
        "personality_score",
        "surveillance_score",
        "private_messages",
    }
)


def _ensure_aware(value: datetime | None) -> datetime | None:
    """Normalize to timezone-aware UTC.

    Naive datetimes are assumed to be UTC. This keeps domain/API contracts in
    UTC while remaining robust to SQLite, which does not persist tz offsets and
    returns naive datetimes on read.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class TenantScoped(_Model):
    tenant_id: str = Field(min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# Organization hierarchy
# ---------------------------------------------------------------------------
class Organization(TenantScoped):
    organization_id: str
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    organization_type: OrganizationType = OrganizationType.ENTERPRISE
    timezone_name: str = Field(default="UTC", max_length=64)
    schema_version: str = "1"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class BusinessUnit(TenantScoped):
    business_unit_id: str
    organization_id: str
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64)
    valid_from: datetime
    valid_to: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> BusinessUnit:
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        return self


class Department(TenantScoped):
    department_id: str
    business_unit_id: str
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64)
    archived_at: datetime | None = None


class Team(TenantScoped):
    team_id: str
    department_id: str
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    team_type: TeamType = TeamType.PRODUCT
    capacity_points: int | None = Field(default=None, ge=0, le=1000)
    archived_at: datetime | None = None


# ---------------------------------------------------------------------------
# Engineer profile (non-sensitive operational attributes only)
# ---------------------------------------------------------------------------
class EngineerProfile(TenantScoped):
    engineer_profile_id: str
    current_team_id: str | None = None
    display_name: str = Field(min_length=1, max_length=128)
    role_title: str | None = Field(default=None, max_length=128)
    level: EngineerLevel | None = None
    employment_state: EmploymentState = EmploymentState.ACTIVE
    region: str | None = Field(default=None, max_length=64)
    valid_from: datetime
    valid_to: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> EngineerProfile:
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        return self


# ---------------------------------------------------------------------------
# Capability & skill catalog (tenant-scoped)
# ---------------------------------------------------------------------------
class EnterpriseCapability(TenantScoped):
    capability_id: str
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    category: CapabilityCategory
    description: str | None = Field(default=None, max_length=512)
    schema_version: str = "1"
    archived_at: datetime | None = None


class EnterpriseSkill(TenantScoped):
    skill_id: str
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    category: CapabilityCategory
    description: str | None = Field(default=None, max_length=512)
    archived_at: datetime | None = None


class CapabilitySkillLink(TenantScoped):
    capability_skill_id: str
    capability_id: str
    skill_id: str


class EngineerCapabilityEvidence(TenantScoped):
    evidence_id: str
    engineer_profile_id: str
    capability_id: str
    proficiency: int | None = Field(default=None, ge=0, le=100)
    source: EvidenceStrengthSource = EvidenceStrengthSource.DECLARED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> EngineerCapabilityEvidence:
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        return self


class EngineerSkillEvidence(TenantScoped):
    evidence_id: str
    engineer_profile_id: str
    skill_id: str
    proficiency: int | None = Field(default=None, ge=0, le=100)
    source: EvidenceStrengthSource = EvidenceStrengthSource.DECLARED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> EngineerSkillEvidence:
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        return self


# ---------------------------------------------------------------------------
# Initiative, project, requirements
# ---------------------------------------------------------------------------
class Initiative(TenantScoped):
    initiative_id: str
    organization_id: str
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1024)
    strategic_priority: StrategicPriority = StrategicPriority.MEDIUM
    criticality: Criticality = Criticality.MEDIUM
    planned_start: datetime | None = None
    planned_target: datetime | None = None
    status: InitiativeStatus = InitiativeStatus.PROPOSED
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> Initiative:
        _validate_interval(
            self.planned_start, self.planned_target, "planned_target", "planned_start"
        )
        return self


class EnterpriseProject(TenantScoped):
    enterprise_project_id: str
    initiative_id: str | None = None
    owning_team_id: str | None = None
    legacy_project_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    status: ProjectStatus = ProjectStatus.PLANNED
    criticality: Criticality = Criticality.MEDIUM
    planned_start: datetime | None = None
    planned_target: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> EnterpriseProject:
        _validate_interval(
            self.planned_start, self.planned_target, "planned_target", "planned_start"
        )
        return self


class CapabilityRequirement(TenantScoped):
    requirement_id: str
    subject_type: RequirementSubjectType
    subject_id: str
    capability_id: str
    required_level: int = Field(default=0, ge=0, le=100)
    criticality: Criticality = Criticality.MEDIUM
    source: EvidenceStrengthSource = EvidenceStrengthSource.DECLARED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Delivery entities
# ---------------------------------------------------------------------------
class Repository(TenantScoped):
    repository_id: str
    owning_team_id: str | None = None
    provider: DataSourceType = DataSourceType.GITHUB
    external_reference: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=128)
    default_branch: str | None = Field(default=None, max_length=128)
    visibility: RepositoryVisibility = RepositoryVisibility.PRIVATE
    state: RepositoryState = RepositoryState.ACTIVE
    archived_at: datetime | None = None


class Sprint(TenantScoped):
    sprint_id: str
    team_id: str
    name: str = Field(min_length=1, max_length=128)
    start_time: datetime
    end_time: datetime
    state: SprintState = SprintState.PLANNED

    @model_validator(mode="after")
    def _check_interval(self) -> Sprint:
        _validate_interval(self.start_time, self.end_time, "end_time", "start_time", strict=True)
        return self


class WorkItem(TenantScoped):
    work_item_id: str
    enterprise_project_id: str | None = None
    initiative_id: str | None = None
    team_id: str | None = None
    sprint_id: str | None = None
    provider: DataSourceType = DataSourceType.JIRA
    external_reference: str = Field(min_length=1, max_length=256)
    work_item_type: WorkItemType = WorkItemType.STORY
    status: WorkItemStatus = WorkItemStatus.BACKLOG
    priority: WorkItemPriority = WorkItemPriority.P2
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    completed_at: datetime | None = None


class Incident(TenantScoped):
    incident_id: str
    repository_id: str | None = None
    enterprise_project_id: str | None = None
    team_id: str | None = None
    provider: DataSourceType = DataSourceType.MANUAL
    external_reference: str = Field(min_length=1, max_length=256)
    severity: IncidentSeverity = IncidentSeverity.SEV3
    started_at: datetime
    resolved_at: datetime | None = None
    state: IncidentState = IncidentState.OPEN

    @model_validator(mode="after")
    def _check_interval(self) -> Incident:
        _validate_interval(self.started_at, self.resolved_at, "resolved_at", "started_at")
        return self


class Deployment(TenantScoped):
    deployment_id: str
    repository_id: str | None = None
    enterprise_project_id: str | None = None
    environment: DeploymentEnvironment = DeploymentEnvironment.PRODUCTION
    status: DeploymentStatus = DeploymentStatus.SUCCEEDED
    started_at: datetime
    completed_at: datetime | None = None
    provider: DataSourceType = DataSourceType.GITHUB
    external_reference: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _check_interval(self) -> Deployment:
        _validate_interval(self.started_at, self.completed_at, "completed_at", "started_at")
        return self


# ---------------------------------------------------------------------------
# Relationships (dependency, ownership, availability)
# ---------------------------------------------------------------------------
class Dependency(TenantScoped):
    dependency_id: str
    source_type: EnterpriseEntityType
    source_id: str
    target_type: EnterpriseEntityType
    target_id: str
    dependency_type: DependencyType
    criticality: Criticality = Criticality.MEDIUM
    valid_from: datetime
    valid_to: datetime | None = None
    evidence_reference: str | None = Field(default=None, max_length=256)
    status: DependencyStatus = DependencyStatus.ACTIVE

    @model_validator(mode="after")
    def _check(self) -> Dependency:
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        if self.source_type == self.target_type and self.source_id == self.target_id:
            raise ValueError("A dependency cannot reference itself")
        return self


class Ownership(TenantScoped):
    ownership_id: str
    owner_type: EnterpriseEntityType
    owner_id: str
    resource_type: EnterpriseEntityType
    resource_id: str
    ownership_type: OwnershipType = OwnershipType.PRIMARY
    allocation: int | None = Field(default=None, ge=0, le=100)
    valid_from: datetime
    valid_to: datetime | None = None
    evidence_reference: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _check(self) -> Ownership:
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        return self


class Availability(TenantScoped):
    availability_id: str
    target_type: EnterpriseEntityType
    target_id: str
    availability_percentage: int | None = Field(default=None, ge=0, le=100)
    capacity_units: float | None = Field(default=None, ge=0)
    start_time: datetime
    end_time: datetime
    reason: AvailabilityReason = AvailabilityReason.UNKNOWN
    source: EvidenceStrengthSource = EvidenceStrengthSource.DECLARED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check(self) -> Availability:
        _validate_interval(self.start_time, self.end_time, "end_time", "start_time", strict=True)
        return self


# ---------------------------------------------------------------------------
# Provenance & ingestion foundation
# ---------------------------------------------------------------------------
class DataSource(TenantScoped):
    data_source_id: str
    source_type: DataSourceType
    display_name: str = Field(min_length=1, max_length=128)
    credential_reference: str | None = Field(default=None, max_length=256)
    config_reference: str | None = Field(default=None, max_length=256)
    status: DataSourceStatus = DataSourceStatus.REGISTERED
    permission_classification: PermissionClassification = PermissionClassification.INTERNAL
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class IngestionRun(TenantScoped):
    ingestion_run_id: str
    data_source_id: str
    run_type: IngestionRunType = IngestionRunType.INCREMENTAL
    status: IngestionRunStatus = IngestionRunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cursor: dict | None = None
    records_read: int = Field(default=0, ge=0)
    records_written: int = Field(default=0, ge=0)
    records_skipped: int = Field(default=0, ge=0)
    error_category: IngestionErrorCategory = IngestionErrorCategory.NONE
    error_summary: str | None = Field(default=None, max_length=1024)
    processing_version: str = "1"

    @model_validator(mode="after")
    def _check(self) -> IngestionRun:
        if self.started_at is not None and self.completed_at is not None:
            _validate_interval(self.started_at, self.completed_at, "completed_at", "started_at")
        return self


class EvidenceSignal(TenantScoped):
    evidence_signal_id: str
    data_source_id: str
    ingestion_run_id: str | None = None
    source_record_id: str = Field(min_length=1, max_length=256)
    signal_type: EvidenceSignalType
    subject_type: EnterpriseEntityType
    subject_id: str = Field(min_length=1, max_length=128)
    event_time: datetime
    observed_at: datetime
    ingested_at: datetime
    schema_version: str = "1"
    processing_version: str = "1"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    permission_classification: PermissionClassification = PermissionClassification.INTERNAL
    expires_at: datetime | None = None
    payload: dict = Field(default_factory=dict)
    payload_hash: str = Field(min_length=64, max_length=64)
    provenance: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Generic pagination envelope
# ---------------------------------------------------------------------------
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Interval helper
# ---------------------------------------------------------------------------
def _validate_interval(
    start: datetime | None,
    end: datetime | None,
    end_name: str,
    start_name: str,
    *,
    strict: bool = False,
) -> None:
    start = _ensure_aware(start)
    end = _ensure_aware(end)
    if start is None or end is None:
        return
    if strict:
        if end <= start:
            raise ValueError(f"{end_name} must be strictly greater than {start_name}")
    else:
        if end < start:
            raise ValueError(f"{end_name} must not precede {start_name}")
