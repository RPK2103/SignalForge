"""Provider selection and failure handling for Leadership Brief generation."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.domain.leadership_brief_models import (
    GenerationStatus,
    LeadershipBrief,
    LeadershipBriefEvidencePackage,
    LeadershipBriefFailureCategory,
    ProviderMode,
)
from app.services.leadership_brief.azure_provider import AzureLeadershipBriefProvider
from app.services.leadership_brief.fallback_provider import DeterministicFallbackProvider
from app.services.leadership_brief.grounding_validator import GroundingValidationError
from app.services.leadership_brief.parser import parse_leadership_brief
from app.services.leadership_brief.prompt_templates import PromptBundle, load_prompt_bundle
from app.services.leadership_brief.provider_interface import (
    LeadershipBriefProvider,
    ProviderAuthenticationError,
    ProviderError,
    ProviderMalformedOutputError,
    ProviderRateLimitError,
    ProviderSchemaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
)


@dataclass(frozen=True)
class LeadershipBriefGenerationOutcome:
    brief: LeadershipBrief
    provider_mode: ProviderMode
    generation_status: GenerationStatus
    failure_category: LeadershipBriefFailureCategory | None
    prompt_version: str


class LeadershipBriefOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        azure_provider: LeadershipBriefProvider | None = None,
        fallback_provider: LeadershipBriefProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._azure_provider = azure_provider or AzureLeadershipBriefProvider(settings=self._settings)
        self._fallback_provider = fallback_provider or DeterministicFallbackProvider()

    def generate(
        self,
        package: LeadershipBriefEvidencePackage,
    ) -> LeadershipBriefGenerationOutcome:
        prompt_bundle = load_prompt_bundle(package)
        evidence_json = package.model_dump_json()

        if not self._settings.ai_enabled:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.AI_DISABLED,
            )
        if not self._settings.azure_openai_configured():
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.MISSING_CONFIGURATION,
            )

        try:
            result = self._azure_provider.generate(
                evidence_package_json=evidence_json,
                prompt_bundle=prompt_bundle,
            )
            if not result.raw_content.strip():
                return self._fallback(
                    package,
                    prompt_bundle,
                    evidence_json,
                    LeadershipBriefFailureCategory.EMPTY_OUTPUT,
                )
            brief = parse_leadership_brief(result.raw_content)
            if brief.provider_mode != ProviderMode.AZURE_OPENAI:
                raise ProviderSchemaError("azure provider returned non-azure mode")
            self._validate_grounding(brief, package, ProviderMode.AZURE_OPENAI)
            return LeadershipBriefGenerationOutcome(
                brief=brief,
                provider_mode=ProviderMode.AZURE_OPENAI,
                generation_status=GenerationStatus.GENERATED,
                failure_category=None,
                prompt_version=prompt_bundle.prompt_version,
            )
        except ProviderTimeoutError:
            return self._fallback(
                package, prompt_bundle, evidence_json, LeadershipBriefFailureCategory.TIMEOUT
            )
        except ProviderAuthenticationError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.AUTHENTICATION_ERROR,
            )
        except ProviderRateLimitError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.RATE_LIMITED,
            )
        except ProviderUnavailableError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.PROVIDER_UNAVAILABLE,
            )
        except ProviderMalformedOutputError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.MALFORMED_OUTPUT,
            )
        except GroundingValidationError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.GROUNDING_VALIDATION_FAILED,
            )
        except ProviderSchemaError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.SCHEMA_VALIDATION_FAILED,
            )
        except ProviderUnknownError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.UNKNOWN_PROVIDER_ERROR,
            )
        except ProviderError:
            return self._fallback(
                package,
                prompt_bundle,
                evidence_json,
                LeadershipBriefFailureCategory.UNKNOWN_PROVIDER_ERROR,
            )

    def _fallback(
        self,
        package: LeadershipBriefEvidencePackage,
        prompt_bundle: PromptBundle,
        evidence_json: str,
        failure_category: LeadershipBriefFailureCategory,
    ) -> LeadershipBriefGenerationOutcome:
        if failure_category == LeadershipBriefFailureCategory.MALFORMED_OUTPUT:
            category = LeadershipBriefFailureCategory.MALFORMED_OUTPUT
        result = self._fallback_provider.generate(
            evidence_package_json=evidence_json,
            prompt_bundle=prompt_bundle,
        )
        if not result.raw_content.strip():
            raise ProviderMalformedOutputError("fallback produced empty output")
        brief = parse_leadership_brief(result.raw_content)
        self._validate_grounding(
            brief,
            package,
            ProviderMode.DETERMINISTIC_FALLBACK,
        )
        return LeadershipBriefGenerationOutcome(
            brief=brief,
            provider_mode=ProviderMode.DETERMINISTIC_FALLBACK,
            generation_status=GenerationStatus.FALLBACK_GENERATED,
            failure_category=failure_category,
            prompt_version=prompt_bundle.prompt_version,
        )

    @staticmethod
    def _validate_grounding(
        brief: LeadershipBrief,
        package: LeadershipBriefEvidencePackage,
        expected_mode: ProviderMode,
    ) -> None:
        from app.services.leadership_brief.grounding_validator import validate_grounding

        validate_grounding(brief, package, expected_provider_mode=expected_mode)
