from fastapi import FastAPI
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router)
app.include_router(health_router)

@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint that redirects to the dashboard.
    """
    return {"message": "Welcome to AUTOBOT API", "docs_url": "/docs"}

@app.get("/predict", tags=["predict"])
async def predict():
    """
    Placeholder endpoint that returns a simulated prediction.
    """
    return {"prediction": 0.5}
