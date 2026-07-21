"""Tests for legacy adapter compatibility."""

from app.adapters.legacy_mapper import (
    legacy_coverage_percentage,
    legacy_engineer_to_domain,
    legacy_project_to_domain,
    legacy_risk_level_from_coverage,
    legacy_team_to_domain,
)
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService


KAVI = {
    "name": "Kavi",
    "experience": 5,
    "skills": ["Azure", "Python", "Generative AI"],
    "certifications": ["Oracle Generative AI"],
    "projects": ["Azure AI Migration", "LLM Pipeline"],
}

AZURE_AI_PROJECT = {
    "name": "Azure AI Migration",
    "required_skills": ["Azure", "Python", "Generative AI"],
    "description": "Migrate workloads to Azure and deploy generative AI capabilities.",
}


def test_legacy_mapper_produces_domain_models():
    from app.schemas.engineer import EngineerProfile
    from app.schemas.project_fit import ProjectRequirements

    engineer = EngineerProfile.model_validate(KAVI)
    project = ProjectRequirements.model_validate(AZURE_AI_PROJECT)
    domain_engineer = legacy_engineer_to_domain(engineer)
    domain_project = legacy_project_to_domain(project)
    assert domain_engineer.name == "Kavi"
    assert len(domain_project.requirements) == 3


def test_legacy_coverage_percentage_full_team():
    from app.schemas.engineer import EngineerProfile
    from app.schemas.project_fit import ProjectRequirements

    engineer = EngineerProfile.model_validate(KAVI)
    project = ProjectRequirements.model_validate(AZURE_AI_PROJECT)
    domain_project, domain_team = legacy_team_to_domain(project, [engineer])
    results = CapabilityCoverageService().analyze(domain_project, domain_team)
    coverage = legacy_coverage_percentage(results, len(project.required_skills))
    assert coverage == 100


def test_legacy_risk_level_thresholds():
    assert legacy_risk_level_from_coverage(80) == "Low"
    assert legacy_risk_level_from_coverage(75) == "Medium"
    assert legacy_risk_level_from_coverage(60) == "High"
