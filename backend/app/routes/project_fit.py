from fastapi import APIRouter

from app.schemas.project_fit import ProjectFitRequest, ProjectFitResult
from app.services.fit_recommender import recommend_project_fit

router = APIRouter()


@router.post("/project-fit", response_model=ProjectFitResult)
def project_fit(request: ProjectFitRequest) -> ProjectFitResult:
    return recommend_project_fit(request)
