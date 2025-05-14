"""
Health check routes for AUTOBOT.
"""
from fastapi import APIRouter, Response, status
from typing import Dict, Any

from ..health import get_health, get_system_info

router = APIRouter(tags=["Health"])

@router.get("/health", summary="Health check endpoint")
def health_check(response: Response) -> Dict[str, Any]:
    """
    Health check endpoint for monitoring system health.
    
    Returns:
        Dict: Health status information
    """
    health_data = get_health()
    
    if health_data["status"] == "healthy":
        response.status_code = status.HTTP_200_OK
        return {"status": "ok"}
    elif health_data["status"] in ["warning", "unhealthy"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    return health_data

@router.get("/health/system", summary="System information")
def system_info() -> Dict[str, Any]:
    """
    Get detailed system information.
    
    Returns:
        Dict: System information
    """
    return get_system_info()
