from fastapi import FastAPI
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router)
app.include_router(health_router)
app.include_router(prediction_router)

@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint that redirects to the dashboard.
    """
    return {"message": "Welcome to AUTOBOT API", "docs_url": "/docs"}
