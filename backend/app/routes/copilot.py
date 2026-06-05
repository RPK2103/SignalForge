from fastapi import APIRouter

from app.schemas.copilot import CopilotRequest, CopilotResponse
from app.services.copilot import answer_copilot_question

router = APIRouter()


@router.post(
    "/copilot",
    response_model=CopilotResponse,
    summary="AI leadership copilot for project execution questions",
    response_description=(
        "Executive-friendly answer grounded in team, risk, fit, and success signals."
    ),
)
def copilot_endpoint(request: CopilotRequest) -> CopilotResponse:
    """Natural-language copilot for engineering leaders.

    Example request::

        {
          "project_name": "Azure AI Migration",
          "question": "Why is this project likely to succeed?"
        }
    """
    return answer_copilot_question(request)
