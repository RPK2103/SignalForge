from functools import lru_cache

from openai import AzureOpenAI

from app.core.config import get_settings


@lru_cache
def get_azure_openai_client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def create_chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 300,
    temperature: float = 0.4,
) -> str:
    settings = get_settings()
    client = get_azure_openai_client()
    response = client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    return (content or "").strip()
