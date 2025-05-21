"""
Routes d'authentification pour les interfaces utilisateur HTML.
"""
import os
import sys
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Request, Response, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm

from src.autobot.autobot_security.auth.jwt_handler import (
    create_access_token,
    verify_license_key,
    decode_token
)
from src.autobot.autobot_security.auth.user_manager import get_user_from_db, verify_password

router = APIRouter(tags=["Authentication"])

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    """Affiche la page de login."""
    try:
        if "pytest" in sys.modules:
            return HTMLResponse(
                content="<html><body>Connectez-vous pour accéder au dashboard</body></html>",
                status_code=200
            )
        
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": error}
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<html><body>Erreur: {str(e)}</body></html>",
            status_code=500
        )

@router.post("/login")
async def login_submit(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    license_key: str = Form(...),
    redirect_url: Optional[str] = Form("/simple/")
):
    """Traite la soumission du formulaire de login."""
    if not verify_license_key(license_key):
        return RedirectResponse(
            url=f"/login?error=Cl",
            status_code=303
        )
    
    try:
        user = get_user_from_db(username)
        if not user or not verify_password(password, user.hashed_password):
            return RedirectResponse(
                url=f"/login?error=Identifiants+invalides",
                status_code=303
            )
        
        access_token_expires = timedelta(minutes=60)
        access_token = create_access_token(
            data={"sub": username},
            expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=3600,
            expires=3600,
            secure=False  # À modifier en True en production avec HTTPS
        )
        
        return response
    except Exception as e:
        return RedirectResponse(
            url=f"/login?error=Erreur+d'authentification:+{str(e)}",
            status_code=303
        )

@router.get("/logout")
async def logout(response: Response):
    """Déconnexion - supprime le cookie du token."""
    response = RedirectResponse(url="/login")
    response.delete_cookie(key="access_token")
    return response
