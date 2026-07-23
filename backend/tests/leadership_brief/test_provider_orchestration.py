"""Provider orchestration tests."""

import pytest

from app.core.config import Settings
from app.domain.leadership_brief_models import (
    GenerationStatus,
    LeadershipBriefFailureCategory,
    ProviderMode,
)
from app.services.leadership_brief.fallback_provider import DeterministicFallbackProvider
from app.services.leadership_brief.orchestrator import LeadershipBriefOrchestrator
from app.services.leadership_brief.provider_interface import (
    ProviderAuthenticationError,
    ProviderMalformedOutputError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
)
from tests.leadership_brief.conftest import FakeAzureProvider, sample_evidence_package, valid_brief_from_package


class TestProviderOrchestration:
    def test_valid_azure_result(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(brief.model_dump_json()),
        )
        outcome = orchestrator.generate(package)
        assert outcome.provider_mode == ProviderMode.AZURE_OPENAI
        assert outcome.generation_status == GenerationStatus.GENERATED
        assert outcome.failure_category is None

    def test_ai_disabled(self):
        orchestrator = LeadershipBriefOrchestrator(settings=Settings(AI_ENABLED=False))
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.provider_mode == ProviderMode.DETERMINISTIC_FALLBACK
        assert outcome.failure_category == LeadershipBriefFailureCategory.AI_DISABLED

    def test_missing_configuration(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(AI_ENABLED=True, AZURE_OPENAI_ENDPOINT="", AZURE_OPENAI_API_KEY="")
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.MISSING_CONFIGURATION

    def test_timeout_fallback(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(error=ProviderTimeoutError("timeout")),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.TIMEOUT

    def test_authentication_failure(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(error=ProviderAuthenticationError("auth")),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.AUTHENTICATION_ERROR

    def test_rate_limit(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(error=ProviderRateLimitError("rate")),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.RATE_LIMITED

    def test_provider_unavailable(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(error=ProviderUnavailableError("down")),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.PROVIDER_UNAVAILABLE

    def test_malformed_output(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider("{bad json"),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.MALFORMED_OUTPUT

    def test_empty_output(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(""),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.EMPTY_OUTPUT

    def test_grounding_failure(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        bad_ref = "risk:deadbeefdeadbeef"
        brief.top_risks[0].evidence_references = [bad_ref]
        brief.staffing_actions[0].evidence_references = [bad_ref]
        brief.mitigation_actions[0].evidence_references = [bad_ref]
        brief.evidence_references = [bad_ref]
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(brief.model_dump_json()),
        )
        outcome = orchestrator.generate(package)
        assert outcome.failure_category == LeadershipBriefFailureCategory.GROUNDING_VALIDATION_FAILED

    def test_unknown_provider_exception(self):
        orchestrator = LeadershipBriefOrchestrator(
            settings=Settings(
                AI_ENABLED=True,
                AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
                AZURE_OPENAI_API_KEY="key",
                AZURE_OPENAI_DEPLOYMENT="deployment",
            ),
            azure_provider=FakeAzureProvider(error=ProviderUnknownError("boom")),
        )
        outcome = orchestrator.generate(sample_evidence_package())
        assert outcome.failure_category == LeadershipBriefFailureCategory.UNKNOWN_PROVIDER_ERROR
