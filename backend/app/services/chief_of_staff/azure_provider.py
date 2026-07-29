"""Azure OpenAI provider for Chief of Staff (no SDK types leak into domain)."""

from __future__ import annotations

import time

from app.core.config import Settings, get_settings
from app.domain.chief_of_staff_enums import ChiefOfStaffProviderMode
from app.services.ai_service import get_azure_openai_client
from app.services.chief_of_staff.prompt_templates import PromptBundle
from app.services.chief_of_staff.provider_interface import (
    CosProviderAuthenticationError,
    CosProviderGenerationResult,
    CosProviderRateLimitError,
    CosProviderTimeoutError,
    CosProviderUnavailableError,
    CosProviderUnknownError,
)


class AzureChiefOfStaffProvider:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def generate(
        self,
        *,
        evidence_package_json: str,
        prompt_bundle: PromptBundle,
    ) -> CosProviderGenerationResult:
        _ = evidence_package_json  # already embedded in user prompt
        client = get_azure_openai_client()
        deployment = self._settings.azure_openai_deployment
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=deployment,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt_bundle.system_prompt},
                    {"role": "user", "content": prompt_bundle.user_prompt},
                ],
                timeout=self._settings.ai_request_timeout_seconds,
            )
        except Exception as exc:  # map explicitly without swallowing
            mapped = self._map_exception(exc)
            raise mapped from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        return CosProviderGenerationResult(
            raw_content=content,
            provider_mode=ChiefOfStaffProviderMode.AZURE_OPENAI,
            metadata={"source": "azure_openai"},
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_deployment_id=deployment,
        )

    @staticmethod
    def _map_exception(exc: Exception) -> Exception:
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        if "timeout" in name or "timeout" in message:
            return CosProviderTimeoutError(str(exc))
        if "auth" in name or "unauthorized" in message or "401" in message:
            return CosProviderAuthenticationError(str(exc))
        if "rate" in name or "429" in message:
            return CosProviderRateLimitError(str(exc))
        if "connect" in name or "unavailable" in message or "503" in message:
            return CosProviderUnavailableError(str(exc))
        return CosProviderUnknownError(str(exc))
