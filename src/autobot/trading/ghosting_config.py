import os
from enum import Enum
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class GhostingMode(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    STEALTH = "stealth"

class GhostingConfig:
    def __init__(self):
        self.always_active = True
        self.mode = GhostingMode.ACTIVE
        self.detection_avoidance = True
        self.max_instances = 10
        self.rotation_interval = 300
        
    def get_config(self) -> Dict[str, Any]:
        return {
            "always_active": self.always_active,
            "mode": self.mode.value,
            "detection_avoidance": self.detection_avoidance,
            "max_instances": self.max_instances,
            "rotation_interval": self.rotation_interval,
            "status": "CONSTANTLY_ACTIVE"
        }
    
    def ensure_always_active(self):
        if not self.always_active:
            logger.warning("Ghosting was not active - forcing activation for platform detection avoidance")
            self.always_active = True
            self.mode = GhostingMode.ACTIVE
        
        return self.always_active

ghosting_config = GhostingConfig()
