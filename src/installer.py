"""
AUTOBOT Installer

This module handles the installation and configuration of AUTOBOT components.
"""

import os
import sys
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def configure_superagi(
    enabled: bool = True,
    api_key: Optional[str] = None,
    base_url: Optional[str] = "https://api.superagi.com",
    config_path: Optional[str] = None
) -> bool:
    """
    Configure SuperAGI integration.
    
    Args:
        enabled: Whether SuperAGI integration is enabled
        api_key: SuperAGI API key
        base_url: SuperAGI API base URL
        config_path: Path to the configuration file
        
    Returns:
        bool: True if configuration was successful
    """
    if not config_path:
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "superagi_config.yaml")
    
    try:
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        
        config["enabled"] = enabled
        if api_key:
            config["api_key"] = api_key
        if base_url:
            config["base_url"] = base_url
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"SuperAGI configuration saved to {config_path}")
        return True
    
    except Exception as e:
        logger.error(f"Error configuring SuperAGI: {str(e)}")
        return False

def main():
    """Main installer function."""
    configure_superagi()
    
    
    logger.info("AUTOBOT installation completed successfully")

if __name__ == "__main__":
    main()
