"""Enterprise data-foundation ORM models (Phase 3 Prompt 1).

Shared-schema multi-tenancy: every tenant-owned table carries a non-null,
indexed ``tenant_id`` and composite uniqueness is always tenant-qualified so a
slug or external reference is unique *within* a tenant, never globally.

These ORM objects never leave the persistence layer; repositories translate
them into ``app.domain.enterprise_models`` DTOs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _TenantBase(Base):
    """Abstract base carrying the tenant boundary and lifecycle timestamps."""

    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# Organization hierarchy
# ---------------------------------------------------------------------------
class Organization(_TenantBase):
    __tablename__ = "ent_organizations"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_ent_organizations_tenant"),
        UniqueConstraint("tenant_id", "slug", name="uq_ent_organizations_tenant_slug"),
    )

    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BusinessUnit(_TenantBase):
    __tablename__ = "ent_business_units"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_ent_business_units_tenant_code"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="valid_interval",
        ),
    )

    business_unit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_organizations.organization_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Department(_TenantBase):
    __tablename__ = "ent_departments"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_ent_departments_tenant_code"),)

    department_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_unit_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_business_units.business_unit_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Team(_TenantBase):
    __tablename__ = "ent_teams"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_ent_teams_tenant_slug"),
        CheckConstraint(
            "capacity_points IS NULL OR (capacity_points >= 0 AND capacity_points <= 1000)",
            name="capacity_bounds",
        ),
    )

    team_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    department_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_departments.department_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    team_type: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Engineer profile
# ---------------------------------------------------------------------------
class EngineerProfile(_TenantBase):
    __tablename__ = "ent_engineer_profiles"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="valid_interval",
        ),
    )

    engineer_profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_team_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_teams.team_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    employment_state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Capability & skill catalog
# ---------------------------------------------------------------------------
class EnterpriseCapability(_TenantBase):
    __tablename__ = "ent_capabilities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_ent_capabilities_tenant_slug"),
    )

    capability_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EnterpriseSkill(_TenantBase):
    __tablename__ = "ent_skills"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_ent_skills_tenant_slug"),)

    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CapabilitySkill(_TenantBase):
    __tablename__ = "ent_capability_skills"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "capability_id",
            "skill_id",
            name="uq_ent_capability_skills_unique",
        ),
    )

    capability_skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capability_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_capabilities.capability_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_skills.skill_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class EngineerCapabilityEvidence(_TenantBase):
    __tablename__ = "ent_engineer_capability_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "engineer_profile_id",
            "capability_id",
            "valid_from",
            name="uq_ent_eng_cap_evidence",
        ),
        CheckConstraint(
            "proficiency IS NULL OR (proficiency >= 0 AND proficiency <= 100)",
            name="proficiency_bounds",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_interval"),
    )

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    engineer_profile_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_engineer_profiles.engineer_profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_capabilities.capability_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    proficiency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="declared")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EngineerSkillEvidence(_TenantBase):
    __tablename__ = "ent_engineer_skill_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "engineer_profile_id",
            "skill_id",
            "valid_from",
            name="uq_ent_eng_skill_evidence",
        ),
        CheckConstraint(
            "proficiency IS NULL OR (proficiency >= 0 AND proficiency <= 100)",
            name="proficiency_bounds",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_interval"),
    )

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    engineer_profile_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_engineer_profiles.engineer_profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_skills.skill_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    proficiency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="declared")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Initiative, project, requirements
# ---------------------------------------------------------------------------
class Initiative(_TenantBase):
    __tablename__ = "ent_initiatives"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_ent_initiatives_tenant_slug"),)

    initiative_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_organizations.organization_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategic_priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_target: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EnterpriseProject(_TenantBase):
    __tablename__ = "ent_projects"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_ent_projects_tenant_slug"),)

    enterprise_project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    initiative_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_initiatives.initiative_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owning_team_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_teams.team_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Provider-neutral link to the immutable Phase 2 project catalog. Not a FK so
    # historical Phase 2 rows are never mutated or cascade-affected.
    legacy_project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_target: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CapabilityRequirement(_TenantBase):
    __tablename__ = "ent_capability_requirements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "capability_id",
            name="uq_ent_capability_requirements",
        ),
        CheckConstraint(
            "required_level >= 0 AND required_level <= 100", name="required_level_bounds"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),
    )

    requirement_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_capabilities.capability_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="declared")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


# ---------------------------------------------------------------------------
# Delivery entities
# ---------------------------------------------------------------------------
class Repository(_TenantBase):
    __tablename__ = "ent_repositories"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "external_reference", name="uq_ent_repositories_external"
        ),
    )

    repository_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owning_team_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_teams.team_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Sprint(_TenantBase):
    __tablename__ = "ent_sprints"
    __table_args__ = (
        UniqueConstraint("tenant_id", "team_id", "name", name="uq_ent_sprints_team_name"),
        CheckConstraint("end_time > start_time", name="sprint_interval"),
    )

    sprint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_teams.team_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")


class WorkItem(_TenantBase):
    __tablename__ = "ent_work_items"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "external_reference", name="uq_ent_work_items_external"
        ),
        Index("ix_ent_work_items_project", "tenant_id", "enterprise_project_id"),
    )

    work_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_projects.enterprise_project_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    initiative_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_initiatives.initiative_id", ondelete="SET NULL"),
        nullable=True,
    )
    team_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_teams.team_id", ondelete="SET NULL"),
        nullable=True,
    )
    sprint_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_sprints.sprint_id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    work_item_type: Mapped[str] = mapped_column(String(16), nullable=False, default="story")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="p2")
    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Incident(_TenantBase):
    __tablename__ = "ent_incidents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "external_reference", name="uq_ent_incidents_external"
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= started_at", name="incident_interval"
        ),
    )

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repository_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_repositories.repository_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    enterprise_project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_projects.enterprise_project_id", ondelete="SET NULL"),
        nullable=True,
    )
    team_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_teams.team_id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="sev3")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")


class Deployment(_TenantBase):
    __tablename__ = "ent_deployments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "external_reference", name="uq_ent_deployments_external"
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="deployment_interval"
        ),
    )

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repository_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_repositories.repository_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    enterprise_project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_projects.enterprise_project_id", ondelete="SET NULL"),
        nullable=True,
    )
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="production")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="succeeded")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(256), nullable=False)


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------
class Dependency(_TenantBase):
    __tablename__ = "ent_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "dependency_type",
            name="uq_ent_dependencies_edge",
        ),
        CheckConstraint(
            "source_type <> target_type OR source_id <> target_id",
            name="no_self_dependency",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_interval"),
    )

    dependency_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dependency_type: Mapped[str] = mapped_column(String(32), nullable=False)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class Ownership(_TenantBase):
    __tablename__ = "ent_ownerships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "owner_type",
            "owner_id",
            "resource_type",
            "resource_id",
            "ownership_type",
            name="uq_ent_ownerships_edge",
        ),
        CheckConstraint(
            "allocation IS NULL OR (allocation >= 0 AND allocation <= 100)",
            name="allocation_bounds",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_interval"),
    )

    ownership_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ownership_type: Mapped[str] = mapped_column(String(16), nullable=False, default="primary")
    allocation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)


class Availability(_TenantBase):
    __tablename__ = "ent_availabilities"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "target_type",
            "target_id",
            "start_time",
            name="uq_ent_availabilities_window",
        ),
        CheckConstraint("end_time > start_time", name="availability_interval"),
        CheckConstraint(
            "availability_percentage IS NULL "
            "OR (availability_percentage >= 0 AND availability_percentage <= 100)",
            name="availability_percentage_bounds",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),
    )

    availability_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    availability_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="declared")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


# ---------------------------------------------------------------------------
# Provenance & ingestion
# ---------------------------------------------------------------------------
class DataSource(_TenantBase):
    __tablename__ = "ent_data_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "display_name", name="uq_ent_data_sources_name"
        ),
    )

    data_source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Opaque, future-safe reference to a secret store. NEVER a plaintext secret.
    credential_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    config_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="registered")
    permission_classification: Mapped[str] = mapped_column(
        String(16), nullable=False, default="internal"
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngestionRun(_TenantBase):
    __tablename__ = "ent_ingestion_runs"
    __table_args__ = (Index("ix_ent_ingestion_runs_source", "tenant_id", "data_source_id"),)

    ingestion_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data_source_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_data_sources.data_source_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(String(16), nullable=False, default="incremental")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_category: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")


class EvidenceSignal(_TenantBase):
    __tablename__ = "ent_evidence_signals"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "source_record_id",
            "signal_type",
            "payload_hash",
            name="uq_ent_evidence_signals_dedup",
        ),
        Index("ix_ent_evidence_signals_subject", "tenant_id", "subject_type", "subject_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),
    )

    evidence_signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data_source_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_data_sources.data_source_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ingestion_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("ent_ingestion_runs.ingestion_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    processing_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    permission_classification: Mapped[str] = mapped_column(
        String(16), nullable=False, default="internal"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
