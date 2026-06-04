from fastapi import APIRouter

from app.schemas.insight import InsightRequest, InsightResponse
from app.services.insight_generator import generate_insight

router = APIRouter()


@router.post("/generate-insight", response_model=InsightResponse)
def generate_insight_endpoint(request: InsightRequest) -> InsightResponse:
    return generate_insight(request)
