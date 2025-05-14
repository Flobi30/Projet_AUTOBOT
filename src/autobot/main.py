from fastapi import FastAPI
from autobot.router_clean import router

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router)

@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint to verify the service is running.
    """
    return {"status": "ok"}

@app.get("/predict", tags=["predict"])
async def predict():
    """
    Placeholder endpoint that returns a simulated prediction.
    """
    return {"prediction": 0.5}
