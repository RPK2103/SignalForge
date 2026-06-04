from fastapi import HTTPException

from app.core.config import get_settings
from app.schemas.insight import InsightRequest, InsightResponse
from app.services.ai_service import create_chat_completion

SYSTEM_PROMPT = """You are an executive advisor for engineering leaders at SignalForge.
Write a single concise executive summary paragraph for an engineering manager.
Cover why the engineer fits the project, delivery risk, team capability coverage, and overall execution confidence.
Use clear, confident language suitable for a leadership briefing.
Respond with plain text only: no bullet points, headings, or markdown.
Limit the response to 80-120 words."""


def _build_user_prompt(request: InsightRequest) -> str:
    coverage = ", ".join(request.team_coverage) if request.team_coverage else "none listed"
    return (
        f"Engineer: {request.engineer_name}\n"
        f"Project: {request.project_name}\n"
        f"Project fit score: {request.fit_score}/100\n"
        f"Delivery risk level: {request.risk_level}\n"
        f"Team capability coverage: {coverage}\n\n"
        "Generate the executive insight."
    )


def generate_insight(request: InsightRequest) -> InsightResponse:
    settings = get_settings()
    if not settings.azure_openai_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT."
            ),
        )

    try:
        insight = create_chat_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(request),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Azure OpenAI request failed: {exc}",
        ) from exc

    if not insight:
        raise HTTPException(
            status_code=502,
            detail="Azure OpenAI returned an empty insight.",
        )

    return InsightResponse(insight=insight)
