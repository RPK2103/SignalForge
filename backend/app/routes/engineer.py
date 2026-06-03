from fastapi import APIRouter

from app.schemas.engineer import EngineerAnalysis, EngineerProfile
from app.services.analyzer import analyze_engineer

router = APIRouter()


@router.post("/analyze", response_model=EngineerAnalysis)
def analyze(profile: EngineerProfile) -> EngineerAnalysis:
    return analyze_engineer(profile)
