"""
Routes pour l'interface utilisateur AUTOBOT
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from autobot.autobot_security.auth.jwt_handler import get_current_user
from autobot.autobot_security.auth.user_manager import User, UserManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])


@router.post("/api/save-settings", response_class=JSONResponse)
async def save_settings(request: Request, current_user: User = Depends(get_current_user)):
    """
    Endpoint pour sauvegarder les paramètres utilisateur.
    
    Args:
        request: Request object
        current_user: Authenticated user
        
    Returns:
        JSONResponse: Status of the save operation
    """
    try:
        data = await request.json()
        
        required_sections = ["general", "api", "trading", "security"]
        for section in required_sections:
            if section not in data:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Section de paramètres requise manquante: {section}"
                )
        
        if "api" in data:
            api_settings = data["api"]
            user_manager = UserManager()
            
            for key_name in ["binance-api-key", "binance-api-secret", "openai-api-key", 
                            "superagi-api-key", "stripe-api-key"]:
                if key_name in api_settings and api_settings[key_name]:
                    field_name = key_name.replace("-", "_")
                    user_manager.update_user_data(
                        user_id=current_user.id,
                        field=field_name,
                        value=api_settings[key_name]
                    )
        
        user_manager = UserManager()
        user_manager.update_user_data(
            user_id=current_user.id,
            field="preferences",
            value=data
        )
        
        logger.info(f"Settings saved successfully for user {current_user.username}")
        
        return {
            "status": "success",
            "message": "Paramètres enregistrés avec succès"
        }
        
    except HTTPException as e:
        logger.error(f"Settings save error: {str(e)}")
        return JSONResponse(
            status_code=e.status_code,
            content={"status": "error", "message": e.detail}
        )
    except Exception as e:
        logger.error(f"Unexpected error saving settings: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erreur lors de la sauvegarde des paramètres: {str(e)}"}
        )
