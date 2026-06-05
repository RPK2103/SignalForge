from pydantic import BaseModel, Field


class SuccessPredictionRequest(BaseModel):
    """Request delivery success prediction for a project.

    Example:
        {
          "project_name": "Azure AI Migration"
        }
    """

    project_name: str = Field(
        ...,
        examples=["Azure AI Migration"],
        description="Name of the project to evaluate (must exist in mock catalog).",
    )


class SuccessPredictionResponse(BaseModel):
    project_name: str
    success_probability: int = Field(
        ge=0,
        le=100,
        examples=[91],
        description="Estimated probability of successful delivery (0–100).",
    )
    confidence: str = Field(
        examples=["High"],
        description="Prediction confidence derived from success probability.",
    )
    delivery_outlook: str = Field(
        examples=["Likely Success"],
        description="Executive delivery outlook label.",
    )
    reasoning: list[str] = Field(
        examples=[
            [
                "Full capability coverage",
                "Low delivery risk",
                "Strong AI capability",
                "Highly qualified team",
            ]
        ],
        description="Deterministic factors driving the prediction.",
    )
    summary: str = Field(
        examples=[
            "This project has a high likelihood of successful execution due to strong "
            "skill coverage, low delivery risk, and a well-balanced engineering team."
        ],
        description="Executive summary of the delivery prediction.",
    )
