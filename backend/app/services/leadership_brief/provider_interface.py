"""Provider interface and typed provider exceptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.leadership_brief_models import ProviderMode
from app.services.leadership_brief.prompt_templates import PromptBundle


class ProviderError(Exception):
    """Base provider error."""


class ProviderTimeoutError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderMalformedOutputError(ProviderError):
    pass


class ProviderSchemaError(ProviderError):
    pass


class ProviderUnknownError(ProviderError):
    pass


@dataclass(frozen=True)
class ProviderGenerationResult:
    raw_content: str
    provider_mode: ProviderMode
    metadata: dict[str, object] = field(default_factory=dict)
    duration_ms: int | None = None


class LeadershipBriefProvider(Protocol):
    def generate(
        self,
        *,
        evidence_package_json: str,
        prompt_bundle: PromptBundle,
    ) -> ProviderGenerationResult: ...
