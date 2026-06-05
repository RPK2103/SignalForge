from fastapi import APIRouter

from app.schemas.predictor import SuccessPredictionRequest, SuccessPredictionResponse
from app.services.predictor import predict_success

router = APIRouter()


@router.post(
    "/success-prediction",
    response_model=SuccessPredictionResponse,
    summary="Predict project delivery success probability",
    response_description=(
        "Success probability, confidence, delivery outlook, reasoning, and executive summary."
    ),
)
def success_prediction_endpoint(
    request: SuccessPredictionRequest,
) -> SuccessPredictionResponse:
    """Estimate delivery success for a project using deterministic team and risk signals.

    Combines capability coverage, delivery risk, and recommended team quality from
    existing SignalForge features.

    Example request::

        {
          "project_name": "Azure AI Migration"
        }
    """
    return predict_success(request)
