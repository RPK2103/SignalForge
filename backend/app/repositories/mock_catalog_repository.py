"""Mock catalog repository backed by demo data."""

from app.adapters.legacy_mapper import (
    legacy_engineers_to_domain,
    legacy_project_to_domain,
)
from app.data.mock_catalog import MOCK_ENGINEERS, MOCK_PROJECTS
from app.domain.models import EngineerProfile, ProjectProfile
from app.schemas.engineer import EngineerProfile as LegacyEngineerProfile
from app.schemas.project_fit import ProjectRequirements


class MockCatalogRepository:
    def list_engineer_names(self) -> list[str]:
        return sorted(MOCK_ENGINEERS.keys())

    def get_legacy_engineer(self, name: str) -> LegacyEngineerProfile | None:
        canonical = self.resolve_engineer_name(name)
        if canonical is None:
            return None
        return MOCK_ENGINEERS[canonical]

    def list_legacy_engineers(self) -> list[LegacyEngineerProfile]:
        return list(MOCK_ENGINEERS.values())

    def get_legacy_project(self, name: str) -> ProjectRequirements | None:
        return MOCK_PROJECTS.get(name.strip())

    def resolve_engineer_name(self, name: str) -> str | None:
        normalized = name.strip().lower()
        for canonical in MOCK_ENGINEERS:
            if canonical.lower() == normalized:
                return canonical
        return None

    def get_domain_engineers(self) -> list[EngineerProfile]:
        return legacy_engineers_to_domain(list(MOCK_ENGINEERS.values()))

    def get_domain_engineer_by_id(self, engineer_id: str) -> EngineerProfile | None:
        normalized = engineer_id.strip().lower()
        for profile in self.get_domain_engineers():
            if profile.id == normalized:
                return profile
        return None

    def get_domain_project(self, name: str) -> ProjectProfile | None:
        project = self.get_legacy_project(name)
        if project is None:
            return None
        return legacy_project_to_domain(project)

    def get_domain_project_by_id(self, project_id: str) -> ProjectProfile | None:
        normalized = project_id.strip().lower()
        for project in self.list_domain_projects():
            if project.id == normalized:
                return project
        return None

    def list_domain_projects(self) -> list[ProjectProfile]:
        return [legacy_project_to_domain(project) for project in MOCK_PROJECTS.values()]
