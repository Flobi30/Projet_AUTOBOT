"""
Plugins module for AUTOBOT.

This module contains plugin functionality for the AUTOBOT system.
"""

from typing import Dict, Any, Callable, List

_PLUGINS: Dict[str, Dict[str, Callable]] = {
    "ai": {},
    "trading": {},
    "ecommerce": {},
    "general": {}
}

def register_plugin(category: str, name: str, plugin_func: Callable) -> None:
    """
    Register a plugin.
    
    Args:
        category: Category of the plugin (ai, trading, ecommerce, general)
        name: Name of the plugin
        plugin_func: Plugin function
    """
    if category not in _PLUGINS:
        _PLUGINS[category] = {}
    
    _PLUGINS[category][name] = plugin_func

def get_plugin(category: str, name: str) -> Callable:
    """
    Get a plugin by category and name.
    
    Args:
        category: Category of the plugin
        name: Name of the plugin
        
    Returns:
        Plugin function
        
    Raises:
        KeyError: If the plugin is not found
    """
    if category not in _PLUGINS or name not in _PLUGINS[category]:
        raise KeyError(f"Plugin {name} in category {category} not found")
    
    return _PLUGINS[category][name]

def list_plugins(category: str = None) -> Dict[str, List[str]]:
    """
    List available plugins.
    
    Args:
        category: Category to list plugins for (None for all categories)
        
    Returns:
        Dict of plugin names by category
    """
    if category:
        if category not in _PLUGINS:
            return {}
        return {category: list(_PLUGINS[category].keys())}
    
    return {cat: list(plugins.keys()) for cat, plugins in _PLUGINS.items()}
