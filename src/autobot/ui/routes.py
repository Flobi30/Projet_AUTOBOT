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
from autobot.autobot_security.auth.user_manager import User

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

@router.get("/backtest", response_class=HTMLResponse)
async def get_backtest(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de backtest.
    """
    return templates.TemplateResponse("backtest.html", {
        "request": request,
        "active_page": "backtest",
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

@router.get("/setup", response_class=HTMLResponse)
async def get_setup(request: Request):
    """
    Page de configuration initiale.
    """
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "active_page": "setup"
    })

@router.get("/backtests", response_class=HTMLResponse)
async def get_backtests(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de backtests automatiques.
    """
    return templates.TemplateResponse("backtests.html", {
        "request": request,
        "active_page": "backtests",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/operations", response_class=HTMLResponse)
async def get_operations(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page d'opérations (trading live + backtests continus).
    """
    return templates.TemplateResponse("operations.html", {
        "request": request,
        "active_page": "operations",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/ghosting", response_class=HTMLResponse)
async def get_ghosting(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de gestion du ghosting.
    """
    return templates.TemplateResponse("ghosting.html", {
        "request": request,
        "active_page": "ghosting",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/licence", response_class=HTMLResponse)
async def get_licence(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de gestion de licence.
    """
    return templates.TemplateResponse("licence.html", {
        "request": request,
        "active_page": "licence",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })

@router.get("/logs", response_class=HTMLResponse)
async def get_logs(request: Request, current_user: User = Depends(get_current_user)):
    """
    Page de logs et monitoring.
    """
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "active_page": "logs",
        "username": current_user.username,
        "user_role": current_user.role,
        "user_role_display": "Administrateur" if current_user.role == "admin" else "Utilisateur"
    })
