from fastapi import FastAPI

from app.routes.engineer import router as engineer_router
from app.routes.project_fit import router as project_fit_router

app = FastAPI(title="SignalForge API")

app.include_router(engineer_router, tags=["Engineer Analysis"])
app.include_router(project_fit_router, tags=["Project Fit"])

@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}