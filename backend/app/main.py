from fastapi import FastAPI

from app.routes.engineer import router as engineer_router

app = FastAPI(title="SignalForge API")

app.include_router(engineer_router, tags=["Engineer Analysis"])

@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}