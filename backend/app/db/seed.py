"""Idempotent catalog and scenario seed command."""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.legacy_mapper import legacy_engineer_to_domain, legacy_project_to_domain
from app.data.mock_catalog import MOCK_ENGINEERS, MOCK_PROJECTS
from app.db.models.catalog import Capability, Engineer, EngineerCapability, Project, ProjectRequirement
from app.db.models.scenario import DemoScenario
from app.db.session import init_engine, session_scope
from app.domain.capability_registry import STANDARD_CAPABILITIES
from app.domain.enums import ScenarioType
from app.domain.simulation_models import CompareSimulationOperation, RemoveSimulationOperation


SCHEMA_VERSION = "1"

EXTRA_PROJECTS = {
    "cloud_modernization": {
        "name": "Cloud Modernization",
        "description": "Modernize legacy workloads onto cloud-native platforms.",
        "requirements": [
            ("azure", True),
            ("kubernetes", True),
            ("terraform", False),
        ],
    },
    "legacy_backend_refactor": {
        "name": "Legacy Backend Refactor",
        "description": "Refactor monolithic backend services into maintainable modules.",
        "requirements": [
            ("java", True),
            ("python", False),
            ("architecture", True),
        ],
    },
    "data_platform_migration": {
        "name": "Data Platform Migration",
        "description": "Migrate analytics pipelines to a modern data platform.",
        "requirements": [
            ("sql", True),
            ("azure", True),
            ("architecture", False),
        ],
    },
    "genai_assistant_build": {
        "name": "GenAI Assistant Build",
        "description": "Build a production generative AI assistant.",
        "requirements": [
            ("generative_ai", True),
            ("python", True),
            ("azure", True),
        ],
    },
}


def _seed_capabilities(session: Session) -> int:
    created = 0
    for cap_id, definition in STANDARD_CAPABILITIES.items():
        row = session.get(Capability, cap_id)
        if row is None:
            session.add(
                Capability(
                    capability_id=cap_id,
                    name=definition.name,
                    description=f"{definition.name} capability",
                    category=definition.category.value,
                    schema_version=SCHEMA_VERSION,
                )
            )
            created += 1
        else:
            row.name = definition.name
            row.category = definition.category.value
            row.description = f"{definition.name} capability"
    return created


def _seed_engineers(session: Session) -> int:
    created = 0
    for legacy in MOCK_ENGINEERS.values():
        domain = legacy_engineer_to_domain(legacy)
        row = session.get(Engineer, domain.id)
        if row is None:
            row = Engineer(
                engineer_id=domain.id,
                name=domain.name,
                experience_years=domain.experience_years,
                has_certifications=domain.has_certifications,
                has_project_history=domain.has_project_history,
                schema_version=SCHEMA_VERSION,
            )
            session.add(row)
            created += 1
        else:
            row.name = domain.name
            row.experience_years = domain.experience_years
            row.has_certifications = domain.has_certifications
            row.has_project_history = domain.has_project_history

        existing_caps = {
            cap.capability_id
            for cap in session.scalars(
                select(EngineerCapability).where(
                    EngineerCapability.engineer_id == domain.id
                )
            ).all()
        }
        for cap in domain.capabilities:
            if cap.capability_id in existing_caps:
                existing = session.scalar(
                    select(EngineerCapability).where(
                        EngineerCapability.engineer_id == domain.id,
                        EngineerCapability.capability_id == cap.capability_id,
                    )
                )
                if existing:
                    existing.proficiency = cap.proficiency
                    existing.evidence_sources = [s.value for s in cap.evidence_sources]
            else:
                session.add(
                    EngineerCapability(
                        engineer_id=domain.id,
                        capability_id=cap.capability_id,
                        proficiency=cap.proficiency,
                        evidence_sources=[s.value for s in cap.evidence_sources],
                    )
                )
    return created


def _seed_project(session: Session, project_id: str, name: str, description: str, requirements) -> None:
    row = session.get(Project, project_id)
    if row is None:
        row = Project(
            project_id=project_id,
            name=name,
            description=description,
            schema_version=SCHEMA_VERSION,
        )
        session.add(row)
    else:
        row.name = name
        row.description = description

    existing_reqs = {
        req.capability_id
        for req in session.scalars(
            select(ProjectRequirement).where(ProjectRequirement.project_id == project_id)
        ).all()
    }
    for capability_id, critical in requirements:
        if capability_id in existing_reqs:
            existing = session.scalar(
                select(ProjectRequirement).where(
                    ProjectRequirement.project_id == project_id,
                    ProjectRequirement.capability_id == capability_id,
                )
            )
            if existing:
                existing.critical = critical
        else:
            session.add(
                ProjectRequirement(
                    project_id=project_id,
                    capability_id=capability_id,
                    required_level=0,
                    weight=1.0,
                    critical=critical,
                )
            )


def _seed_projects(session: Session) -> int:
    created = 0
    for legacy in MOCK_PROJECTS.values():
        domain = legacy_project_to_domain(legacy)
        if session.get(Project, domain.id) is None:
            created += 1
        _seed_project(
            session,
            domain.id,
            domain.name,
            legacy.description,
            [(req.capability_id, req.critical) for req in domain.requirements],
        )

    for project_id, payload in EXTRA_PROJECTS.items():
        if session.get(Project, project_id) is None:
            created += 1
        _seed_project(
            session,
            project_id,
            payload["name"],
            payload["description"],
            payload["requirements"],
        )
    return created


def _upsert_scenario(session: Session, **kwargs) -> bool:
    row = session.get(DemoScenario, kwargs["scenario_id"])
    if row is None:
        session.add(DemoScenario(**kwargs))
        return True
    row.name = kwargs["name"]
    row.description = kwargs["description"]
    row.project_id = kwargs["project_id"]
    row.baseline_engineer_ids = kwargs["baseline_engineer_ids"]
    row.simulation_operation = kwargs.get("simulation_operation")
    row.scenario_type = kwargs["scenario_type"]
    return False


def _seed_scenarios(session: Session) -> int:
    created = 0
    scenarios = [
        {
            "scenario_id": "azure_ai_migration",
            "name": "Azure AI Migration",
            "description": "Assess readiness for Azure AI migration with the core demo team.",
            "project_id": "azure_ai_migration",
            "baseline_engineer_ids": ["kavi", "vikram"],
            "simulation_operation": None,
            "scenario_type": ScenarioType.READINESS.value,
        },
        {
            "scenario_id": "cloud_modernization",
            "name": "Cloud Modernization",
            "description": "Evaluate cloud modernization readiness.",
            "project_id": "cloud_modernization",
            "baseline_engineer_ids": ["kavi", "vikram", "arjun"],
            "simulation_operation": None,
            "scenario_type": ScenarioType.READINESS.value,
        },
        {
            "scenario_id": "legacy_backend_refactor",
            "name": "Legacy Backend Refactor",
            "description": "Assess backend refactor readiness.",
            "project_id": "legacy_backend_refactor",
            "baseline_engineer_ids": ["vikram", "arjun"],
            "simulation_operation": None,
            "scenario_type": ScenarioType.READINESS.value,
        },
        {
            "scenario_id": "data_platform_migration",
            "name": "Data Platform Migration",
            "description": "Assess data platform migration readiness.",
            "project_id": "data_platform_migration",
            "baseline_engineer_ids": ["kavi", "arjun"],
            "simulation_operation": None,
            "scenario_type": ScenarioType.READINESS.value,
        },
        {
            "scenario_id": "genai_assistant_build",
            "name": "GenAI Assistant Build",
            "description": "Assess GenAI assistant delivery readiness.",
            "project_id": "genai_assistant_build",
            "baseline_engineer_ids": ["kavi", "vikram"],
            "simulation_operation": None,
            "scenario_type": ScenarioType.READINESS.value,
        },
        {
            "scenario_id": "critical_engineer_exit",
            "name": "Critical Engineer Exit",
            "description": "Simulate removing a critical engineer from the team.",
            "project_id": "azure_ai_migration",
            "baseline_engineer_ids": ["kavi", "vikram"],
            "simulation_operation": RemoveSimulationOperation(engineer_id="kavi").model_dump(
                mode="json"
            ),
            "scenario_type": ScenarioType.SIMULATION.value,
        },
        {
            "scenario_id": "understaffed_team",
            "name": "Understaffed Team",
            "description": "Assess a single-engineer understaffed team.",
            "project_id": "azure_ai_migration",
            "baseline_engineer_ids": ["kavi"],
            "simulation_operation": None,
            "scenario_type": ScenarioType.READINESS.value,
        },
        {
            "scenario_id": "balanced_team",
            "name": "Balanced Team",
            "description": "Compare a balanced baseline team against an alternate roster.",
            "project_id": "azure_ai_migration",
            "baseline_engineer_ids": ["kavi", "vikram"],
            "simulation_operation": CompareSimulationOperation(
                proposed_engineer_ids=["kavi", "vikram", "arjun"]
            ).model_dump(mode="json"),
            "scenario_type": ScenarioType.SIMULATION.value,
        },
    ]
    for payload in scenarios:
        if _upsert_scenario(session, **payload):
            created += 1
    return created


def seed_database(session: Session) -> dict[str, int]:
    return {
        "capabilities_created": _seed_capabilities(session),
        "engineers_created": _seed_engineers(session),
        "projects_created": _seed_projects(session),
        "scenarios_created": _seed_scenarios(session),
    }


def main() -> int:
    init_engine()
    try:
        with session_scope() as session:
            summary = seed_database(session)
    except Exception as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Seed complete: "
        f"capabilities={summary['capabilities_created']}, "
        f"engineers={summary['engineers_created']}, "
        f"projects={summary['projects_created']}, "
        f"scenarios={summary['scenarios_created']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
