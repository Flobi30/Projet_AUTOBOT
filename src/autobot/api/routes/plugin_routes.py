"""
Plugin routes for AUTOBOT.

This module contains API routes for plugins.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from autobot.autobot_security.auth.jwt_handler import oauth2_scheme, verify_license_key

from autobot.plugins.vairo import get_data as get_vairo
from autobot.plugins.vessium import get_data as get_vessium
from autobot.plugins.confident_ai import get_data as get_confident_ai
from autobot.plugins.doozerai import get_data as get_doozerai
from autobot.plugins.nextvestment import get_data as get_nextvestment
from autobot.plugins.chatvolt import get_data as get_chatvolt
from autobot.plugins.playai import get_data as get_playai
from autobot.plugins.octocomics import get_data as get_octocomics
from autobot.plugins.crewai import get_data as get_crewai
from autobot.plugins.ppe_kit_detection_agents import get_data as get_ppe_kit_detection_agents
from autobot.plugins.langbase import get_data as get_langbase
from autobot.plugins.manus_ai import get_data as get_manus_ai
from autobot.plugins.xagent import get_data as get_xagent
from autobot.plugins.director import get_data as get_director
from autobot.plugins.tensorstax import get_data as get_tensorstax
from autobot.plugins.nurture import get_data as get_nurture
from autobot.plugins.teammates_ai import get_data as get_teammates_ai
from autobot.plugins.bob import get_data as get_bob
from autobot.plugins.shipstation import get_data as get_shipstation
from autobot.plugins.chatgpt import get_data as get_chatgpt
from autobot.plugins.garnit import get_data as get_garnit

router = APIRouter(prefix="/plugins", tags=["plugins"])

@router.get('/vairo')
def plug_vairo(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from Vairo plugin.
    
    Returns:
        Data from the plugin
    """
    return get_vairo()

@router.get('/vessium')
def plug_vessium(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from Vessium plugin.
    
    Returns:
        Data from the plugin
    """
    return get_vessium()

@router.get('/confident_ai')
def plug_confident_ai(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from Confident AI plugin.
    
    Returns:
        Data from the plugin
    """
    return get_confident_ai()

@router.get('/doozerai')
def plug_doozerai(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from Doozer AI plugin.
    
    Returns:
        Data from the plugin
    """
    return get_doozerai()

@router.get('/nextvestment')
def plug_nextvestment(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from Nextvestment plugin.
    
    Returns:
        Data from the plugin
    """
    return get_nextvestment()

@router.get('/chatvolt')
def plug_chatvolt(
    token: str = Depends(oauth2_scheme),
    _ok: bool = Depends(verify_license_key)
): 
    """
    Get data from ChatVolt plugin.
    
    Returns:
        Data from the plugin
    """
    return get_chatvolt()
