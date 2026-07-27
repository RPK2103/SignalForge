"""Deterministic fallback provider tests."""

from uuid import uuid4

from app.domain.leadership_brief_models import (
    GenerationStatus,
    LeadershipDecision,
    ProviderMode,
)
from app.schemas.api_v2 import ReadinessAssessResponse
from app.services.identifiers import build_assessment_id
from app.services.intelligence.readiness_assessment_service import ReadinessAssessmentService
from app.services.leadership_brief.evidence_package import build_evidence_package
from app.services.leadership_brief.fallback_provider import DeterministicFallbackProvider
from app.services.leadership_brief.prompt_templates import PROMPT_VERSION, load_prompt_bundle
from tests.intelligence.fixtures import (
    empty_team_request,
    key_person_request,
)
from tests.leadership_brief.conftest import sample_assessment_result, sample_evidence_package


def _assessment_response_from_domain(
    assessment, *, team, assessment_id: str
) -> ReadinessAssessResponse:
    return ReadinessAssessResponse(
        assessment_id=assessment_id,
        team=team,
        **assessment.model_dump(),
    )


class TestFallbackProvider:
    def test_deterministic_repeatability(self):
        provider = DeterministicFallbackProvider()
        package = sample_evidence_package()
        first = provider.build_brief(package)
        second = provider.build_brief(package)
        assert first.model_dump() == second.model_dump()

    def test_provider_metadata(self):
        provider = DeterministicFallbackProvider()
        package = sample_evidence_package()
        brief = provider.build_brief(package)
        assert brief.provider_mode == ProviderMode.DETERMINISTIC_FALLBACK
        assert brief.generation_status == GenerationStatus.FALLBACK_GENERATED
        assert brief.prompt_version == PROMPT_VERSION

    def test_high_readiness_scenario(self):
        provider = DeterministicFallbackProvider()
        result = sample_assessment_result()
        package = build_evidence_package(assessment_record_id=uuid4(), result=result)
        brief = provider.build_brief(package)
        assert brief.decision in {
            LeadershipDecision.PROCEED,
            LeadershipDecision.PROCEED_WITH_CONDITIONS,
            LeadershipDecision.DEFER,
        }

    def test_severe_blocking_risk_scenario(self):
        service = ReadinessAssessmentService()
        assessment = service.assess(empty_team_request())
        result = _assessment_response_from_domain(
            assessment,
            team=[],
            assessment_id=build_assessment_id("azure_ai_migration", [], "v1"),
        )
        package = build_evidence_package(assessment_record_id=uuid4(), result=result)
        brief = DeterministicFallbackProvider().build_brief(package)
        assert brief.decision in {
            LeadershipDecision.DEFER,
            LeadershipDecision.DO_NOT_PROCEED,
        }

    def test_key_person_dependency(self):
        service = ReadinessAssessmentService()
        assessment = service.assess(key_person_request())
        result = _assessment_response_from_domain(
            assessment,
            team=key_person_request().team.engineers,
            assessment_id=build_assessment_id("azure_ai_migration", ["kavi"], "v1"),
        )
        package = build_evidence_package(assessment_record_id=uuid4(), result=result)
        brief = DeterministicFallbackProvider().build_brief(package)
        assert any(
            action.title.startswith("Reduce key-person") for action in brief.staffing_actions
        )

    def test_every_recommendation_grounded(self):
        provider = DeterministicFallbackProvider()
        package = sample_evidence_package()
        brief = provider.build_brief(package)
        known = {item.evidence_id for item in package.risk_findings} | {
            item.evidence_id for item in package.decision_trace
        }
        for risk in brief.top_risks:
            assert all(ref in known for ref in risk.evidence_references)
        for action in brief.staffing_actions + brief.mitigation_actions:
            assert all(ref in known for ref in action.evidence_references)

    def test_no_invented_engineer(self):
        provider = DeterministicFallbackProvider()
        package = sample_evidence_package()
        brief = provider.build_brief(package)
        for action in brief.staffing_actions + brief.mitigation_actions:
            assert all(engineer in package.team_member_ids for engineer in action.engineer_ids)

    def test_generate_via_provider_interface(self):
        provider = DeterministicFallbackProvider()
        package = sample_evidence_package()
        bundle = load_prompt_bundle(package)
        result = provider.generate(
            evidence_package_json=package.model_dump_json(),
            prompt_bundle=bundle,
        )
        assert result.provider_mode == ProviderMode.DETERMINISTIC_FALLBACK
