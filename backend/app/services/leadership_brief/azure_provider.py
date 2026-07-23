"""Azure OpenAI Leadership Brief provider."""

from __future__ import annotations

import time

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    AzureOpenAI,
    BadRequestError,
    RateLimitError,
)

from app.core.config import Settings, get_settings
from app.domain.leadership_brief_models import ProviderMode
from app.services.ai_service import get_azure_openai_client
from app.services.leadership_brief.prompt_templates import PromptBundle
from app.services.leadership_brief.provider_interface import (
    ProviderAuthenticationError,
    ProviderGenerationResult,
    ProviderMalformedOutputError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
)


class AzureLeadershipBriefProvider:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: AzureOpenAI | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    def generate(
        self,
        *,
        evidence_package_json: str,
        prompt_bundle: PromptBundle,
    ) -> ProviderGenerationResult:
        client = self._client or get_azure_openai_client()
        started = time.perf_counter()
        attempts = max(1, self._settings.ai_max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = client.chat.completions.create(
                    model=self._settings.azure_openai_deployment,
                    messages=[
                        {"role": "system", "content": prompt_bundle.system_prompt},
                        {"role": "user", "content": prompt_bundle.user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=1800,
                    response_format={"type": "json_object"},
                    timeout=self._settings.ai_request_timeout_seconds,
                )
                content = (response.choices[0].message.content or "").strip()
                if not content:
                    raise ProviderMalformedOutputError("empty provider output")
                duration_ms = int((time.perf_counter() - started) * 1000)
                return ProviderGenerationResult(
                    raw_content=content,
                    provider_mode=ProviderMode.AZURE_OPENAI,
                    metadata={"attempt": attempt + 1},
                    duration_ms=duration_ms,
                )
            except ProviderMalformedOutputError:
                raise
            except APITimeoutError as exc:
                raise ProviderTimeoutError(str(exc)) from exc
            except AuthenticationError as exc:
                raise ProviderAuthenticationError(str(exc)) from exc
            except RateLimitError as exc:
                raise ProviderRateLimitError(str(exc)) from exc
            except (APIConnectionError, BadRequestError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise ProviderUnavailableError(str(exc)) from exc
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise ProviderUnknownError(str(exc)) from exc

        raise ProviderUnknownError(str(last_error) if last_error else "unknown provider failure")
