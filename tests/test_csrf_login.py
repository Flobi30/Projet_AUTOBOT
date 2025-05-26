"""
Tests unitaires pour la protection CSRF et l'authentification.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.autobot.main import app

client = TestClient(app)

def test_csrf_token_generation():
    """Vérifie que le token CSRF est généré et inclus dans la page de login."""
    response = client.get("/login")
    assert response.status_code == 200
    assert 'name="csrf_token" value="' in response.text
    assert response.cookies.get("csrf_token") is not None

@patch("src.autobot.routes.auth_routes.verify_license_key")
@patch("src.autobot.routes.auth_routes.get_user_from_db")
@patch("src.autobot.routes.auth_routes.verify_password")
@patch("src.autobot.routes.auth_routes.create_access_token")
def test_login_with_valid_csrf(mock_create_token, mock_verify_pw, mock_get_user, mock_verify_license):
    """Test de connexion avec un token CSRF valide."""
    mock_verify_license.return_value = True
    mock_user = MagicMock()
    mock_user.hashed_password = "hashed_password"
    mock_get_user.return_value = mock_user
    mock_verify_pw.return_value = True
    mock_create_token.return_value = "fake_token"
    
    login_response = client.get("/login")
    csrf_token = login_response.cookies.get("csrf_token")
    
    response = client.post(
        "/login",
        data={
            "username": "testuser",
            "password": "password123",
            "license_key": "LICENSE-KEY",
            "csrf_token": csrf_token,
            "redirect_url": "/dashboard/"
        },
        cookies={"csrf_token": csrf_token},
        allow_redirects=False
    )
    
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/"
    assert "access_token" in response.cookies

@patch("src.autobot.routes.auth_routes.verify_license_key")
@patch("src.autobot.routes.auth_routes.get_user_from_db")
@patch("src.autobot.routes.auth_routes.verify_password")
@patch("src.autobot.routes.auth_routes.create_access_token")
def test_login_with_invalid_csrf(mock_create_token, mock_verify_pw, mock_get_user, mock_verify_license):
    """Test de connexion avec un token CSRF invalide."""
    mock_verify_license.return_value = True
    mock_user = MagicMock()
    mock_get_user.return_value = mock_user
    
    response = client.post(
        "/login",
        data={
            "username": "testuser",
            "password": "password123",
            "license_key": "LICENSE-KEY",
            "csrf_token": "invalid_token",
            "redirect_url": "/dashboard/"
        },
        cookies={"csrf_token": "different_token"},
        allow_redirects=False
    )
    
    assert response.status_code == 303
    assert "error=Erreur+de+sécurité:+Token+CSRF+invalide" in response.headers["location"]

@patch("src.autobot.routes.auth_routes.verify_license_key")
@patch("src.autobot.routes.auth_routes.get_user_from_db")
@patch("src.autobot.routes.auth_routes.verify_password")
@patch("src.autobot.routes.auth_routes.create_access_token")
def test_api_login_without_csrf(mock_create_token, mock_verify_pw, mock_get_user, mock_verify_license):
    """Test de connexion API sans token CSRF."""
    mock_verify_license.return_value = True
    mock_user = MagicMock()
    mock_user.hashed_password = "hashed_password"
    mock_get_user.return_value = mock_user
    mock_verify_pw.return_value = True
    mock_create_token.return_value = "fake_token"
    
    response = client.post(
        "/login",
        data={
            "username": "testuser",
            "password": "password123",
            "license_key": "LICENSE-KEY",
            "redirect_url": "/dashboard/"
        },
        headers={"Content-Type": "application/json"},
        allow_redirects=False
    )
    
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/"
    assert "access_token" in response.cookies
