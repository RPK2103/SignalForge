from fastapi import FastAPI

from app.routes.engineer import router as engineer_router
from app.routes.insight import router as insight_router
from app.routes.project_fit import router as project_fit_router
from app.routes.risk import router as risk_router
from app.routes.simulator import router as simulator_router
from app.routes.team import router as team_router

app = FastAPI(title="SignalForge API")

app.include_router(engineer_router, tags=["Engineer Analysis"])
app.include_router(project_fit_router, tags=["Project Fit"])
app.include_router(risk_router, tags=["Risk Assessment"])
app.include_router(team_router, tags=["Team Recommendation"])
app.include_router(insight_router, tags=["Executive Insight"])
app.include_router(simulator_router, tags=["Staffing Simulator"])

@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}