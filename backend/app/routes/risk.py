from fastapi import APIRouter

from app.schemas.risk import RiskAssessmentRequest, RiskAssessmentResponse
from app.services.risk_assessor import assess_risk

router = APIRouter()


@router.post("/assess-risk", response_model=RiskAssessmentResponse)
def assess_risk_endpoint(request: RiskAssessmentRequest) -> RiskAssessmentResponse:
    return assess_risk(request)
