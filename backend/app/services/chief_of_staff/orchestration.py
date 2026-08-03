"""Provider orchestration for Chief of Staff generation."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.domain.chief_of_staff_constants import FALLBACK_TEMPLATE_VERSION, MAX_PROVIDER_OUTPUT_CHARS
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffFailureCategory,
    ChiefOfStaffGenerationState,
    ChiefOfStaffProviderMode,
    CitationResult,
    GroundingResult,
)
from app.domain.chief_of_staff_models import ChiefOfStaffBrief, ChiefOfStaffEvidencePackage
from app.observability.domain import record_cos_generation
from app.services.chief_of_staff.azure_provider import AzureChiefOfStaffProvider
from app.services.chief_of_staff.fallback import DeterministicFallbackProvider, build_fallback_brief
from app.services.chief_of_staff.grounding import (
    CitationValidationError,
    GroundingValidationError,
    UnsupportedClaimError,
    validate_brief_grounding,
)
from app.services.chief_of_staff.parser import parse_chief_of_staff_brief
from app.services.chief_of_staff.prompt_injection import scan_package_for_injection
from app.services.chief_of_staff.prompt_templates import load_prompt_bundle
from app.services.chief_of_staff.provider_interface import (
    ChiefOfStaffProvider,
    CosProviderAuthenticationError,
    CosProviderError,
    CosProviderMalformedOutputError,
    CosProviderRateLimitError,
    CosProviderSchemaError,
    CosProviderTimeoutError,
    CosProviderUnavailableError,
    CosProviderUnknownError,
)
from app.services.chief_of_staff.responsible_language import (
    ResponsibleLanguageError,
    validate_responsible_language,
)


@dataclass(frozen=True)
class CosGenerationOutcome:
    brief: ChiefOfStaffBrief
    requested_provider: ChiefOfStaffProviderMode
    final_provider: ChiefOfStaffProviderMode
    generation_state: ChiefOfStaffGenerationState
    failure_category: ChiefOfStaffFailureCategory | None
    prompt_version: str
    fallback_template_version: str
    grounding_result: GroundingResult
    citation_result: CitationResult
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    provider_latency_ms: int | None = None
    model_deployment_id: str | None = None


def _emit_generation_telemetry(outcome: CosGenerationOutcome) -> None:
    """Emit bounded, content-free Chief-of-Staff generation telemetry.

    Only provider mode, generation state and bounded failure categories are
    exported — never prompt text, evidence, citation IDs or provider output.
    Fail-open: telemetry never alters the deterministic generation result.
    """
    failure = outcome.failure_category
    is_fallback = outcome.final_provider == ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK
    latency = (
        float(outcome.provider_latency_ms) if outcome.provider_latency_ms is not None else None
    )
    record_cos_generation(
        provider_type=outcome.final_provider.value,
        outcome=outcome.generation_state.value,
        fallback_category=failure.value if (is_fallback and failure is not None) else None,
        provider_latency_ms=latency,
        fallback=is_fallback,
        parse_failure=failure == ChiefOfStaffFailureCategory.MALFORMED_OUTPUT,
        schema_failure=failure == ChiefOfStaffFailureCategory.SCHEMA_VALIDATION_FAILED,
        grounding_failure=outcome.grounding_result == GroundingResult.FAILED,
        unsupported_claim=failure == ChiefOfStaffFailureCategory.UNSUPPORTED_CLAIM_DETECTED,
        citation_failure=failure == ChiefOfStaffFailureCategory.CITATION_VALIDATION_FAILED,
    )


class ChiefOfStaffOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        azure_provider: ChiefOfStaffProvider | None = None,
        fallback_provider: ChiefOfStaffProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._azure_provider = azure_provider or AzureChiefOfStaffProvider(settings=self._settings)
        self._fallback_provider = fallback_provider or DeterministicFallbackProvider()

    def generate(
        self,
        package: ChiefOfStaffEvidencePackage,
        *,
        evidence_package_hash: str | None = None,
        package_id: str | None = None,
        requested_provider: ChiefOfStaffProviderMode,
    ) -> CosGenerationOutcome:
        """Generate a brief and emit exactly one generation telemetry sample.

        The heavy lifting is delegated to :meth:`_run_generation`; telemetry is
        emitted from the resolved outcome so one logical generation produces one
        generation-count metric (substage failures never double-count it).
        """
        outcome = self._run_generation(
            package,
            evidence_package_hash=evidence_package_hash,
            package_id=package_id,
            requested_provider=requested_provider,
        )
        _emit_generation_telemetry(outcome)
        return outcome

    def _run_generation(
        self,
        package: ChiefOfStaffEvidencePackage,
        *,
        evidence_package_hash: str | None = None,
        package_id: str | None = None,
        requested_provider: ChiefOfStaffProviderMode,
    ) -> CosGenerationOutcome:
        """Generate a brief bound to the content-canonical evidence package hash.

        ``package_id`` is accepted as a deprecated alias for
        ``evidence_package_hash`` (must be the package hash, never a DB snapshot PK).
        """
        package_hash = evidence_package_hash or package_id or package.package_hash
        if not package_hash:
            raise ValueError("evidence_package_hash is required")
        if package.package_hash and package_hash != package.package_hash:
            raise ValueError("evidence_package_hash must match package.package_hash")

        prompt_bundle = load_prompt_bundle(package)
        evidence_json = package.model_dump_json()

        injection_hits = scan_package_for_injection(package)
        if injection_hits and requested_provider == ChiefOfStaffProviderMode.AZURE_OPENAI:
            return self._fallback(
                package,
                evidence_package_hash=package_hash,
                requested_provider=requested_provider,
                failure_category=ChiefOfStaffFailureCategory.PROMPT_INJECTION_DETECTED,
                prompt_version=prompt_bundle.prompt_version,
            )

        if requested_provider == ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK:
            return self._fallback(
                package,
                evidence_package_hash=package_hash,
                requested_provider=requested_provider,
                failure_category=None,
                prompt_version=prompt_bundle.prompt_version,
            )

        if not self._settings.ai_enabled:
            return self._fallback(
                package,
                evidence_package_hash=package_hash,
                requested_provider=requested_provider,
                failure_category=ChiefOfStaffFailureCategory.AI_DISABLED,
                prompt_version=prompt_bundle.prompt_version,
            )
        if not self._settings.azure_openai_configured():
            return self._fallback(
                package,
                evidence_package_hash=package_hash,
                requested_provider=requested_provider,
                failure_category=ChiefOfStaffFailureCategory.MISSING_CONFIGURATION,
                prompt_version=prompt_bundle.prompt_version,
            )

        category: ChiefOfStaffFailureCategory | None = None
        grounding_result = GroundingResult.PASSED
        citation_result = CitationResult.PASSED
        try:
            result = self._azure_provider.generate(
                evidence_package_json=evidence_json,
                prompt_bundle=prompt_bundle,
            )
            if not result.raw_content.strip():
                return self._fallback(
                    package,
                    evidence_package_hash=package_hash,
                    requested_provider=requested_provider,
                    failure_category=ChiefOfStaffFailureCategory.EMPTY_OUTPUT,
                    prompt_version=prompt_bundle.prompt_version,
                    provider_latency_ms=result.duration_ms,
                    model_deployment_id=result.model_deployment_id,
                )
            if len(result.raw_content) > MAX_PROVIDER_OUTPUT_CHARS:
                return self._fallback(
                    package,
                    evidence_package_hash=package_hash,
                    requested_provider=requested_provider,
                    failure_category=ChiefOfStaffFailureCategory.OVERSIZED_OUTPUT,
                    prompt_version=prompt_bundle.prompt_version,
                    provider_latency_ms=result.duration_ms,
                    model_deployment_id=result.model_deployment_id,
                )
            brief = parse_chief_of_staff_brief(result.raw_content)
            # Bind citations to content-canonical evidence package hash.
            brief = brief.model_copy(
                update={
                    "citations": [
                        c.model_copy(update={"package_id": package_hash}) for c in brief.citations
                    ],
                    "provider_mode": ChiefOfStaffProviderMode.AZURE_OPENAI,
                    "generation_state": ChiefOfStaffGenerationState.GENERATED,
                    "fallback_visible": False,
                }
            )
            validate_responsible_language(brief)
            validate_brief_grounding(brief, package, evidence_package_hash=package_hash)
            return CosGenerationOutcome(
                brief=brief,
                requested_provider=requested_provider,
                final_provider=ChiefOfStaffProviderMode.AZURE_OPENAI,
                generation_state=ChiefOfStaffGenerationState.GENERATED,
                failure_category=None,
                prompt_version=prompt_bundle.prompt_version,
                fallback_template_version=FALLBACK_TEMPLATE_VERSION,
                grounding_result=GroundingResult.PASSED,
                citation_result=CitationResult.PASSED,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                provider_latency_ms=result.duration_ms,
                model_deployment_id=result.model_deployment_id,
            )
        except CosProviderTimeoutError:
            category = ChiefOfStaffFailureCategory.TIMEOUT
        except CosProviderAuthenticationError:
            category = ChiefOfStaffFailureCategory.AUTHENTICATION_ERROR
        except CosProviderRateLimitError:
            category = ChiefOfStaffFailureCategory.RATE_LIMITED
        except CosProviderUnavailableError:
            category = ChiefOfStaffFailureCategory.PROVIDER_UNAVAILABLE
        except CosProviderMalformedOutputError as exc:
            msg = str(exc).lower()
            if "empty" in msg:
                category = ChiefOfStaffFailureCategory.EMPTY_OUTPUT
            elif "oversized" in msg:
                category = ChiefOfStaffFailureCategory.OVERSIZED_OUTPUT
            else:
                category = ChiefOfStaffFailureCategory.MALFORMED_OUTPUT
        except CosProviderSchemaError:
            category = ChiefOfStaffFailureCategory.SCHEMA_VALIDATION_FAILED
        except UnsupportedClaimError:
            category = ChiefOfStaffFailureCategory.UNSUPPORTED_CLAIM_DETECTED
            grounding_result = GroundingResult.FAILED
        except CitationValidationError:
            category = ChiefOfStaffFailureCategory.CITATION_VALIDATION_FAILED
            citation_result = CitationResult.FAILED
            grounding_result = GroundingResult.FAILED
        except GroundingValidationError:
            category = ChiefOfStaffFailureCategory.GROUNDING_VALIDATION_FAILED
            grounding_result = GroundingResult.FAILED
        except ResponsibleLanguageError:
            category = ChiefOfStaffFailureCategory.UNSUPPORTED_CLAIM_DETECTED
            grounding_result = GroundingResult.FAILED
        except CosProviderUnknownError:
            category = ChiefOfStaffFailureCategory.UNKNOWN_PROVIDER_ERROR
        except CosProviderError:
            category = ChiefOfStaffFailureCategory.UNKNOWN_PROVIDER_ERROR
        else:
            raise RuntimeError("unreachable")

        return self._fallback(
            package,
            evidence_package_hash=package_hash,
            requested_provider=requested_provider,
            failure_category=category,
            prompt_version=prompt_bundle.prompt_version,
            grounding_result=grounding_result,
            citation_result=citation_result,
        )

    def _fallback(
        self,
        package: ChiefOfStaffEvidencePackage,
        *,
        evidence_package_hash: str,
        requested_provider: ChiefOfStaffProviderMode,
        failure_category: ChiefOfStaffFailureCategory | None,
        prompt_version: str,
        provider_latency_ms: int | None = None,
        model_deployment_id: str | None = None,
        grounding_result: GroundingResult = GroundingResult.PASSED,
        citation_result: CitationResult = CitationResult.PASSED,
    ) -> CosGenerationOutcome:
        brief = build_fallback_brief(
            package,
            evidence_package_hash=evidence_package_hash,
            prompt_version=prompt_version,
        )
        validate_brief_grounding(brief, package, evidence_package_hash=evidence_package_hash)
        validate_responsible_language(brief)
        return CosGenerationOutcome(
            brief=brief,
            requested_provider=requested_provider,
            final_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
            generation_state=ChiefOfStaffGenerationState.FALLBACK_GENERATED,
            failure_category=failure_category,
            prompt_version=prompt_version,
            fallback_template_version=FALLBACK_TEMPLATE_VERSION,
            grounding_result=grounding_result,
            citation_result=citation_result,
            provider_latency_ms=provider_latency_ms,
            model_deployment_id=model_deployment_id,
        )
