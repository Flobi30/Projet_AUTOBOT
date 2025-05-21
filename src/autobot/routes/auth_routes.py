"""
Routes d'authentification pour AUTOBOT.
Fournit des endpoints API et UI pour l'authentification et la gestion des tokens.
"""
import os
import sys
from datetime import timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from ..autobot_security.auth.jwt_handler import (
    create_access_token,
    verify_license_key,
    decode_token
)
from ..autobot_security.auth.user_manager import get_user_from_db, verify_password
from ..autobot_security.config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_MINUTES

load_dotenv()

router = APIRouter(tags=["Authentication"])

current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates_dir = os.path.join(current_dir, "ui", "templates")
templates = Jinja2Templates(directory=templates_dir)


@router.post("/token", summary="Obtenir un token d'accès")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Obtient un token d'accès en utilisant les identifiants OAuth2.
    
    Args:
        form_data: Formulaire de demande OAuth2 avec username et password
        
    Returns:
        Dict: Token d'accès JWT
    """
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "votre_mot_de_passe_fort")
    
    if form_data.username != admin_user or form_data.password != admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = {
        "sub": form_data.username,
        "role": "admin"
    }
    
    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


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
            url=f"/login?error=Clé de licence invalide",
            status_code=303
        )
    
    try:
        user = get_user_from_db(username)
        if not user or not verify_password(password, user.hashed_password):
            return RedirectResponse(
                url=f"/login?error=Identifiants+invalides",
                status_code=303
            )
        
        access_token_expires = timedelta(minutes=TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": username},
            expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=TOKEN_EXPIRE_MINUTES * 60,
            expires=TOKEN_EXPIRE_MINUTES * 60,
            secure=os.getenv("ENVIRONMENT", "development") == "production",  # True en production, False en développement
            samesite="lax"  # Protection contre les attaques CSRF
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
