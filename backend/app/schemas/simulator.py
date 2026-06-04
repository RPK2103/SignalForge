from pydantic import BaseModel, Field


class SimulateRequest(BaseModel):
    """Simulate staffing impact when engineers leave the recommended team.

    Example:
        {
          "project_name": "Azure AI Migration",
          "remove_engineers": ["Kavi"]
        }
    """

    project_name: str = Field(
        ...,
        examples=["Azure AI Migration"],
        description="Name of the project to simulate (must exist in mock catalog).",
    )
    remove_engineers: list[str] = Field(
        ...,
        examples=[["Kavi"]],
        description="Engineer names to remove from the recommended team.",
    )


class SimulateResponse(BaseModel):
    project_name: str
    removed_engineers: list[str]
    original_team: list[str]
    remaining_team: list[str]
    lost_capabilities: list[str]
    coverage_before: int = Field(ge=0, le=100)
    coverage_after: int = Field(ge=0, le=100)
    risk_before: str
    risk_after: str
    success_probability_before: int = Field(ge=0, le=100)
    success_probability_after: int = Field(ge=0, le=100)
    impact_score: int = Field(ge=0, le=100)
    simulation_summary: str
