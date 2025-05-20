"""
Monitoring module for AUTOBOT.

This module provides monitoring functionality for the AUTOBOT system.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def get_system_status() -> Dict[str, Any]:
    """
    Get the current system status.
    
    Returns:
        Dict containing system status information
    """
    from autobot.autobot_guardian import get_health
    
    try:
        return get_health()
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        return {"status": "error", "message": str(e)}

def get_system_metrics() -> Dict[str, Any]:
    """
    Get system metrics.
    
    Returns:
        Dict containing system metrics
    """
    from autobot.guardian import get_metrics
    
    try:
        return get_metrics()
    except Exception as e:
        logger.error(f"Error getting system metrics: {str(e)}")
        return {"status": "error", "message": str(e)}

def get_system_logs() -> List[Dict[str, Any]]:
    """
    Get system logs.
    
    Returns:
        List of log entries
    """
    from autobot.guardian import get_logs
    
    try:
        return get_logs()
    except Exception as e:
        logger.error(f"Error getting system logs: {str(e)}")
        return [{"level": "error", "message": f"Error getting logs: {str(e)}"}]
