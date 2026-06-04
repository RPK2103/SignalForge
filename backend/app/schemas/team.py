from pydantic import BaseModel, Field

from app.schemas.engineer import EngineerProfile
from app.schemas.project_fit import ProjectRequirements


class TeamRecommendationRequest(BaseModel):
    project: ProjectRequirements
    engineers: list[EngineerProfile]


class RecommendedEngineer(BaseModel):
    name: str
    fit_score: int = Field(ge=0, le=100)
    role: str


class TeamRecommendationResponse(BaseModel):
    project_name: str
    recommended_team: list[RecommendedEngineer]
    team_coverage: list[str]
    missing_coverage: list[str]
    summary: str
