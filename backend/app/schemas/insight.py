from pydantic import BaseModel, Field


class InsightRequest(BaseModel):
    engineer_name: str
    project_name: str
    fit_score: int = Field(ge=0, le=100)
    risk_level: str
    team_coverage: list[str] = Field(default_factory=list)


class InsightResponse(BaseModel):
    insight: str
