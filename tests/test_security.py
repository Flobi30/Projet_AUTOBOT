"""
Tests unitaires pour la sécurité et l'authentification JWT.
"""
import os
import pytest
import jwt
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends, HTTPException, status
from unittest.mock import patch, MagicMock

from src.autobot.autobot_security.config import SECRET_KEY, ALGORITHM
from src.autobot.autobot_security.auth.jwt_handler import (
    create_access_token, 
    decode_token, 
    get_current_user,
    verify_license_key
)

@pytest.fixture
def test_app():
    from src.autobot.main import app
    return app

@pytest.fixture
def client(test_app):
    return TestClient(test_app)

def test_jwt_creation():
    """Teste la création d'un token JWT."""
    data = {"sub": "testuser"}
    token = create_access_token(data)
    
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "testuser"
    assert "exp" in decoded

def test_jwt_validation():
    """Teste la validation d'un token JWT."""
    data = {"sub": "testuser"}
    token = create_access_token(data)
    
    decoded = decode_token(token)
    assert decoded["sub"] == "testuser"

def test_jwt_expiration():
    """Teste l'expiration d'un token JWT."""
    data = {"sub": "testuser"}
    expired_token = create_access_token(data, expires_delta=timedelta(minutes=-10))
    
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(expired_token)
    
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED

def test_login_endpoint(client):
    """Teste l'endpoint de login."""
    response = client.post(
        "/token", 
        data={"username": "wrong", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 401
    
    with patch('src.autobot.routes.auth_routes.os.getenv') as mock_getenv:
        def mock_env(key, default=None):
            if key == "ADMIN_USER":
                return "admin"
            elif key == "ADMIN_PASSWORD":
                return "admin"
            return default
        
        mock_getenv.side_effect = mock_env
        
        response = client.post(
            "/token", 
            data={"username": "admin", "password": "admin"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

def test_protected_endpoint_access(client):
    """Teste l'accès à un endpoint protégé avec un token valide."""
    token = create_access_token({"sub": "testuser"})
    
    with patch('src.autobot.router_new.get_current_user') as mock_user:
        mock_user.return_value = {"sub": "testuser"}
        
        response = client.get(
            "/api/v1/status", 
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code != 401
        assert response.status_code != 403

def test_protected_endpoint_no_token(client):
    """Teste l'accès à un endpoint protégé sans token."""
    response = client.get("/api/v1/status")
    
    assert response.status_code in [401, 403]

def test_license_key_validation():
    """Teste la validation de la clé de licence."""
    with patch('os.getenv') as mock_getenv:
        mock_getenv.return_value = "VALID-LICENSE-KEY"
        assert verify_license_key("VALID-LICENSE-KEY") == True
        assert verify_license_key("INVALID-LICENSE-KEY") == False

