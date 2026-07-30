"""Provider protocol for Chief of Staff structured generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.chief_of_staff_enums import ChiefOfStaffProviderMode
from app.services.chief_of_staff.prompt_templates import PromptBundle


class CosProviderError(Exception):
    """Base provider error."""


class CosProviderTimeoutError(CosProviderError):
    pass


class CosProviderAuthenticationError(CosProviderError):
    pass


class CosProviderRateLimitError(CosProviderError):
    pass


class CosProviderUnavailableError(CosProviderError):
    pass


class CosProviderMalformedOutputError(CosProviderError):
    pass


class CosProviderSchemaError(CosProviderError):
    pass


class CosProviderUnknownError(CosProviderError):
    pass


@dataclass(frozen=True)
class CosProviderGenerationResult:
    raw_content: str
    provider_mode: ChiefOfStaffProviderMode
    metadata: dict[str, object] = field(default_factory=dict)
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    model_deployment_id: str | None = None


class ChiefOfStaffProvider(Protocol):
    def generate(
        self,
        *,
        evidence_package_json: str,
        prompt_bundle: PromptBundle,
    ) -> CosProviderGenerationResult: ...
