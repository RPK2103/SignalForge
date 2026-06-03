from fastapi import FastAPI

app = FastAPI(title="SignalForge API")

@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}