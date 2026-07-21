"""Fixtures for Phase 2 intelligence domain tests."""

from app.domain.enums import CapabilityCategory, EvidenceSource
from app.domain.models import (
    EngineerCapability,
    EngineerProfile,
    ProjectProfile,
    ProjectRequirement,
    ReadinessAssessmentRequest,
    TeamComposition,
)


def balanced_team_request() -> ReadinessAssessmentRequest:
    return ReadinessAssessmentRequest(
        project=ProjectProfile(
            id="azure_ai_migration",
            name="Azure AI Migration",
            requirements=[
                ProjectRequirement(capability_id="azure", weight=1.0, critical=True),
                ProjectRequirement(capability_id="python", weight=1.0, critical=True),
                ProjectRequirement(capability_id="generative_ai", weight=1.0, critical=True),
            ],
        ),
        team=TeamComposition(
            engineers=[
                EngineerProfile(
                    id="kavi",
                    name="Kavi",
                    experience_years=5,
                    capabilities=[
                        EngineerCapability(
                            capability_id="azure",
                            proficiency=85,
                            evidence_sources=[
                                EvidenceSource.SKILLS,
                                EvidenceSource.CERTIFICATIONS,
                                EvidenceSource.PROJECTS,
                            ],
                        ),
                        EngineerCapability(
                            capability_id="python",
                            proficiency=85,
                            evidence_sources=[EvidenceSource.SKILLS, EvidenceSource.PROJECTS],
                        ),
                        EngineerCapability(
                            capability_id="generative_ai",
                            proficiency=85,
                            evidence_sources=[
                                EvidenceSource.SKILLS,
                                EvidenceSource.CERTIFICATIONS,
                            ],
                        ),
                    ],
                    has_certifications=True,
                    has_project_history=True,
                ),
                EngineerProfile(
                    id="vikram",
                    name="Vikram",
                    experience_years=7,
                    capabilities=[
                        EngineerCapability(
                            capability_id="azure",
                            proficiency=80,
                            evidence_sources=[EvidenceSource.SKILLS, EvidenceSource.CERTIFICATIONS],
                        ),
                        EngineerCapability(
                            capability_id="python",
                            proficiency=75,
                            evidence_sources=[EvidenceSource.SKILLS, EvidenceSource.PROJECTS],
                        ),
                    ],
                    has_certifications=True,
                    has_project_history=True,
                ),
            ]
        ),
    )


def missing_critical_request() -> ReadinessAssessmentRequest:
    request = balanced_team_request()
    request.team.engineers[0].capabilities = [
        cap for cap in request.team.engineers[0].capabilities if cap.capability_id != "generative_ai"
    ]
    request.team.engineers[1].capabilities = [
        cap for cap in request.team.engineers[1].capabilities if cap.capability_id != "generative_ai"
    ]
    return request


def weak_capability_request() -> ReadinessAssessmentRequest:
    request = balanced_team_request()
    for engineer in request.team.engineers:
        for cap in engineer.capabilities:
            if cap.capability_id == "generative_ai":
                cap.proficiency = 30
                cap.evidence_sources = [EvidenceSource.SKILLS]
    return request


def key_person_request() -> ReadinessAssessmentRequest:
    request = balanced_team_request()
    request.team.engineers = [request.team.engineers[0]]
    return request


def duplicate_engineers_request() -> ReadinessAssessmentRequest:
    request = balanced_team_request()
    request.team.engineers.append(request.team.engineers[0].model_copy())
    return request


def empty_team_request() -> ReadinessAssessmentRequest:
    request = balanced_team_request()
    request.team.engineers = []
    return request


def no_requirements_request() -> ReadinessAssessmentRequest:
    request = balanced_team_request()
    request.project.requirements = []
    return request


def incomplete_evidence_request() -> ReadinessAssessmentRequest:
    request = key_person_request()
    request.team.engineers[0].has_certifications = False
    request.team.engineers[0].has_project_history = False
    for cap in request.team.engineers[0].capabilities:
        cap.evidence_sources = [EvidenceSource.SKILLS]
        cap.proficiency = 55
    return request
