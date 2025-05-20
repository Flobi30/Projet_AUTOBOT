"""
Routes d'authentification pour AUTOBOT.
Fournit des endpoints API pour l'authentification et la gestion des tokens.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import os
import json
from datetime import timedelta
from typing import Dict, Any

from ..autobot_security.auth.jwt_handler import create_access_token
from ..autobot_security.config import SECRET_KEY, ALGORITHM

router = APIRouter(tags=["Authentication"])

@router.post("/token", summary="Obtenir un token d'accès")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Obtient un token d'accès en utilisant les identifiants OAuth2.
    
    Args:
        form_data: Formulaire de demande OAuth2 avec username et password
        
    Returns:
        Dict: Token d'accès JWT
    """
    auth_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config', 'auth_config.json')
    
    try:
        with open(auth_config_path, 'r') as f:
            auth_config = json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du chargement de la configuration d'authentification: {str(e)}"
        )
    
    admin_user = auth_config.get("admin_user", "admin")
    admin_password = auth_config.get("admin_password", "votre_mot_de_passe_fort")
    token_expire_minutes = auth_config.get("token_expire_minutes", 1440)
    
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
        expires_delta=timedelta(minutes=token_expire_minutes)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }
