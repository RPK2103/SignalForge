from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes.copilot import router as copilot_router
from app.routes.engineer import router as engineer_router
from app.routes.insight import router as insight_router
from app.routes.project_fit import router as project_fit_router
from app.routes.risk import router as risk_router
from app.routes.predictor import router as predictor_router
from app.routes.simulator import router as simulator_router
from app.routes.team import router as team_router

app = FastAPI(title="SignalForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"
app.mount(
    "/dashboard",
    StaticFiles(directory=str(DASHBOARD_DIR), html=True),
    name="dashboard",
)

app.include_router(engineer_router, tags=["Engineer Analysis"])
app.include_router(project_fit_router, tags=["Project Fit"])
app.include_router(risk_router, tags=["Risk Assessment"])
app.include_router(team_router, tags=["Team Recommendation"])
app.include_router(insight_router, tags=["Executive Insight"])
app.include_router(simulator_router, tags=["Staffing Simulator"])
app.include_router(predictor_router, tags=["Delivery Success Predictor"])
app.include_router(copilot_router, tags=["AI Leadership Copilot"])

@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}