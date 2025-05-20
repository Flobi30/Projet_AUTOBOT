"""
Configuration module for AUTOBOT.

This module handles configuration loading and management.
"""

import os
import json
from typing import Dict, Any, Optional

def load_config(config_file: str) -> Dict[str, Any]:
    """
    Load configuration from a JSON file.
    
    Args:
        config_file: Path to the configuration file
        
    Returns:
        Dict containing the configuration
    """
    if not os.path.exists(config_file):
        return {}
        
    with open(config_file, 'r') as f:
        return json.load(f)
        
def save_config(config_file: str, config: Dict[str, Any]) -> None:
    """
    Save configuration to a JSON file.
    
    Args:
        config_file: Path to the configuration file
        config: Configuration to save
    """
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
        
def get_config_value(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Get a value from a configuration dictionary.
    
    Args:
        config: Configuration dictionary
        key: Key to get
        default: Default value if key is not found
        
    Returns:
        Value for the key or default if not found
    """
    return config.get(key, default)
