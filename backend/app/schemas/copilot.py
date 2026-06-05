from pydantic import BaseModel, Field


class CopilotRequest(BaseModel):
    """Ask SignalForge Copilot a leadership question about a project.

    Example:
        {
          "project_name": "Azure AI Migration",
          "question": "Why is this project likely to succeed?"
        }
    """

    project_name: str = Field(
        ...,
        examples=["Azure AI Migration"],
        description="Name of the project (must exist in mock catalog).",
    )
    question: str = Field(
        ...,
        examples=["Why is this project likely to succeed?"],
        description="Natural-language leadership question about staffing, risk, or delivery.",
    )


class CopilotResponse(BaseModel):
    project_name: str
    question: str
    answer: str = Field(
        examples=[
            "This project is likely to succeed because the recommended team fully covers "
            "Azure, Python, and Generative AI capabilities, delivery risk is low, and the "
            "predicted success probability is 91%."
        ],
        description="Concise executive-friendly answer grounded in project context.",
    )
    sources_used: list[str] = Field(
        examples=[
            [
                "project_fit",
                "risk_assessment",
                "team_recommendation",
                "success_prediction",
            ]
        ],
        description="SignalForge data sources used to build the answer.",
    )
