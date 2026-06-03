from fastapi import FastAPI

from app.routes.engineer import router as engineer_router
from app.routes.project_fit import router as project_fit_router
from app.routes.risk import router as risk_router

app = FastAPI(title="SignalForge API")

app.include_router(engineer_router, tags=["Engineer Analysis"])
app.include_router(project_fit_router, tags=["Project Fit"])
app.include_router(risk_router, tags=["Risk Assessment"])

@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}