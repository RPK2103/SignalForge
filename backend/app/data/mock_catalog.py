"""Deterministic mock projects and engineers for demo endpoints."""

from app.schemas.engineer import EngineerProfile
from app.schemas.project_fit import ProjectRequirements

MOCK_ENGINEERS: dict[str, EngineerProfile] = {
    "Kavi": EngineerProfile(
        name="Kavi",
        experience=5,
        skills=["Azure", "Python", "Generative AI"],
        certifications=["Oracle Generative AI"],
        projects=["Azure AI Migration", "LLM Pipeline"],
    ),
    "Vikram": EngineerProfile(
        name="Vikram",
        experience=7,
        skills=["Azure", "Python"],
        certifications=["Azure Solutions Architect"],
        projects=["Cloud Migration", "AI Platform"],
    ),
    "Arjun": EngineerProfile(
        name="Arjun",
        experience=4,
        skills=["Azure", "Python"],
        certifications=[],
        projects=["API Gateway"],
    ),
}

MOCK_PROJECTS: dict[str, ProjectRequirements] = {
    "Azure AI Migration": ProjectRequirements(
        name="Azure AI Migration",
        required_skills=["Azure", "Python", "Generative AI"],
        description="Migrate workloads to Azure and deploy generative AI capabilities.",
    ),
}
