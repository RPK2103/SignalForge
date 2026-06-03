from pydantic import BaseModel, Field

from app.schemas.engineer import EngineerProfile


class ProjectRequirements(BaseModel):
    name: str
    required_skills: list[str] = Field(default_factory=list)
    description: str = ""


class ProjectFitRequest(BaseModel):
    engineer: EngineerProfile
    project: ProjectRequirements


class ProjectFitResult(BaseModel):
    engineer_name: str
    project_name: str
    fit_score: int = Field(ge=0, le=100)
    recommendation: str
    matched_skills: list[str]
    missing_skills: list[str]
    reasoning: str
