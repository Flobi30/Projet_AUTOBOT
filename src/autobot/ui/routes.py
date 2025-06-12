"""
Routes pour l'interface utilisateur AUTOBOT
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from autobot.autobot_security.auth.jwt_handler import get_current_user
from autobot.autobot_security.auth.user_manager import User, UserManager

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page principale du dashboard.
    """
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/trading", response_class=HTMLResponse)
async def get_trading(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de trading.
    """
    return templates.TemplateResponse("trading.html", {
        "request": request,
        "active_page": "trading",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/ecommerce", response_class=HTMLResponse)
async def get_ecommerce(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page d'e-commerce.
    """
    return templates.TemplateResponse("ecommerce.html", {
        "request": request,
        "active_page": "ecommerce",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/arbitrage", response_class=HTMLResponse)
async def get_arbitrage(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page d'arbitrage.
    """
    return templates.TemplateResponse("arbitrage.html", {
        "request": request,
        "active_page": "arbitrage",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })


@router.get("/capital", response_class=HTMLResponse)
async def get_capital(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de gestion du capital.
    """
    return templates.TemplateResponse("capital.html", {
        "request": request,
        "active_page": "capital",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/duplication", response_class=HTMLResponse)
async def get_duplication(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de duplication d'instances.
    """
    return templates.TemplateResponse("duplication.html", {
        "request": request,
        "active_page": "duplication",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/retrait-depot", response_class=HTMLResponse)
async def get_retrait_depot(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de retrait et dépôt.
    """
    return templates.TemplateResponse("retrait_depot.html", {
        "request": request,
        "active_page": "retrait-depot",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/parametres", response_class=HTMLResponse)
async def get_parametres(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de paramètres.
    """
    return templates.TemplateResponse("parametres.html", {
        "request": request,
        "active_page": "parametres",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

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
