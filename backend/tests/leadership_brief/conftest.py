"""Shared Leadership Brief test helpers."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.domain.leadership_brief_models import (
    GenerationStatus,
    LeadershipActionPriority,
    LeadershipBrief,
    LeadershipBriefAction,
    LeadershipBriefRisk,
    LeadershipBriefRiskSeverity,
    LeadershipDecision,
    ProviderMode,
)
from app.schemas.api_v2 import ReadinessAssessResponse
from app.services.leadership_brief.evidence_package import build_evidence_package
from app.services.leadership_brief.prompt_templates import PROMPT_VERSION, PromptBundle
from app.services.leadership_brief.provider_interface import ProviderGenerationResult
from app.repositories.mock_catalog_repository import MockCatalogRepository
from app.services.readiness_orchestrator import ReadinessOrchestrator
from app.schemas.api_v2 import ReadinessAssessRequest
from tests.intelligence.fixtures import balanced_team_request


def sample_assessment_result() -> ReadinessAssessResponse:
    orchestrator = ReadinessOrchestrator(catalog=MockCatalogRepository())
    request = ReadinessAssessRequest(
        project_id="azure_ai_migration",
        engineer_ids=["kavi", "vikram"],
    )
    return orchestrator.assess(request)


def sample_evidence_package(record_id: UUID | None = None):
    result = sample_assessment_result()
    return build_evidence_package(
        assessment_record_id=record_id or uuid4(),
        result=result,
    )


def valid_brief_from_package(package) -> LeadershipBrief:
    refs = [item.evidence_id for item in package.risk_findings[:2]] or [
        package.decision_trace[0].evidence_id
    ]
    return LeadershipBrief(
        executive_summary="Executive summary grounded in deterministic evidence.",
        decision=LeadershipDecision.PROCEED_WITH_CONDITIONS,
        top_risks=[
            LeadershipBriefRisk(
                title="Critical capability risk",
                explanation="A critical capability gap remains.",
                severity=LeadershipBriefRiskSeverity.HIGH,
                evidence_references=[refs[0]],
            )
        ],
        staffing_actions=[
            LeadershipBriefAction(
                title="Add specialist",
                action="Assign a specialist to close the capability gap.",
                rationale="Deterministic assessment identified a staffing gap.",
                priority=LeadershipActionPriority.HIGH,
                capability_id=package.skill_gaps[0]["capability_id"]
                if package.skill_gaps
                else None,
                engineer_ids=[],
                evidence_references=[refs[0]],
            )
        ],
        mitigation_actions=[
            LeadershipBriefAction(
                title="Mitigate delivery risk",
                action="Execute mitigation before approval.",
                rationale="Risk remains in persisted findings.",
                priority=LeadershipActionPriority.MEDIUM,
                capability_id=None,
                engineer_ids=[],
                evidence_references=[refs[0]],
            )
        ],
        confidence_statement=(
            f"Confidence is {package.confidence_level} at {package.confidence_score}/100."
        ),
        evidence_references=sorted(set(refs)),
        provider_mode=ProviderMode.AZURE_OPENAI,
        prompt_version=PROMPT_VERSION,
        generation_status=GenerationStatus.GENERATED,
    )


class FakeAzureProvider:
    def __init__(self, content: str | None = None, *, error: Exception | None = None) -> None:
        self._content = content
        self._error = error

    def generate(self, *, evidence_package_json: str, prompt_bundle: PromptBundle):
        if self._error is not None:
            raise self._error
        return ProviderGenerationResult(
            raw_content=self._content or "",
            provider_mode=ProviderMode.AZURE_OPENAI,
        )
