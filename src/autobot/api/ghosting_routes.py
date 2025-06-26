from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/api/ghosting/status")
async def get_ghosting_status():
    """Get current ghosting system status"""
    try:
        from ..trading.ghosting_config import ghosting_config
        config = ghosting_config.get_config()
        ghosting_config.ensure_always_active()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "active",
                "mode": "CONSTANTLY_ACTIVE",
                "instances": 3,
                "detection_avoidance": True,
                "uptime": "24/7",
                "always_active": config["always_active"],
                "platform_detection_prevention": True
            }
        )
    except Exception as e:
        logger.error(f"Error getting ghosting status: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving ghosting status")

@router.post("/api/ghosting/activate")
async def activate_ghosting():
    """Ensure ghosting system is active"""
    try:
        from ..trading.ghosting_config import ghosting_config
        ghosting_config.ensure_always_active()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Ghosting system activated and will remain constantly active for platform detection avoidance",
                "mode": "CONSTANTLY_ACTIVE",
                "detection_prevention": True
            }
        )
    except Exception as e:
        logger.error(f"Error activating ghosting: {e}")
        raise HTTPException(status_code=500, detail="Error activating ghosting system")

@router.get("/api/instances")
async def get_instances():
    """Get list of active ghost instances"""
    try:
        mock_instances = [
            {
                "id": "ghost-001",
                "status": "active",
                "market": "BTC/USDT",
                "strategy": "PPO",
                "performance": "+12.4%",
                "uptime": "2d 14h"
            },
            {
                "id": "ghost-002", 
                "status": "active",
                "market": "ETH/USDT",
                "strategy": "DQN",
                "performance": "+8.7%",
                "uptime": "1d 8h"
            },
            {
                "id": "ghost-003",
                "status": "active", 
                "market": "ADA/USDT",
                "strategy": "A2C",
                "performance": "+15.2%",
                "uptime": "3d 2h"
            }
        ]
        
        return JSONResponse(
            status_code=200,
            content={
                "instances": mock_instances,
                "instances_total": len(mock_instances),
                "instances_active": len([i for i in mock_instances if i["status"] == "active"]),
                "instances_performance": "+12.1%"
            }
        )
    except Exception as e:
        logger.error(f"Error getting instances: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving instances")
