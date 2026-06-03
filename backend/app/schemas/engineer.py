from pydantic import BaseModel, Field


class EngineerProfile(BaseModel):
    name: str
    experience: float = Field(ge=0)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


class EngineerAnalysis(BaseModel):
    name: str
    execution: int
    backend: int
    cloud: int
    ai_readiness: int
    strengths: list[str]
    risks: list[str]
    summary: str
