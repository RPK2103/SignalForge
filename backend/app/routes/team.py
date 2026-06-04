from fastapi import APIRouter

from app.schemas.team import TeamRecommendationRequest, TeamRecommendationResponse
from app.services.team_recommender import recommend_team

router = APIRouter()


@router.post("/recommend-team", response_model=TeamRecommendationResponse)
def recommend_team_endpoint(
    request: TeamRecommendationRequest,
) -> TeamRecommendationResponse:
    return recommend_team(request)
