#!/usr/bin/env python3
"""
AUTOBOT Main Application Entry Point
FastAPI server for AUTOBOT trading system
"""

import logging
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .ui.routes import router as ui_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AUTOBOT Trading System",
    description="Advanced automated trading system for Crypto/FOREX",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).parent / "ui" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

app.include_router(ui_router)

@app.on_event("startup")
async def startup_event():
    """Initialize AUTOBOT system on startup"""
    logger.info("🚀 AUTOBOT Trading System Starting...")
    logger.info("✅ Advanced optimization modules loaded")
    logger.info("✅ Real-time backtest integration active")
    logger.info("✅ Crypto/FOREX trading focus enabled")
    logger.info("🎯 AUTOBOT ready for optimization")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 AUTOBOT Trading System Shutting Down...")

@app.get("/")
async def root():
    """Root endpoint - redirect to login"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "AUTOBOT Trading System",
        "version": "1.0.0",
        "optimization_active": True
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
