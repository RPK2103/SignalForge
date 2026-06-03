from pydantic import BaseModel, Field

from app.schemas.engineer import EngineerProfile


class RiskProjectRequirements(BaseModel):
    name: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    domain: str | None = None


class RiskAssessmentRequest(BaseModel):
    engineer: EngineerProfile
    project: RiskProjectRequirements


class RiskAssessmentResponse(BaseModel):
    engineer_name: str
    project_name: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: str
    risks: list[str]
    mitigation_plan: list[str]
    reasoning: str
