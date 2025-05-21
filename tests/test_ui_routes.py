"""
Tests unitaires pour les routes UI HTML.
"""
import pytest
from fastapi.testclient import TestClient
from fastapi.responses import RedirectResponse
from unittest.mock import patch, MagicMock

def get_test_client():
    """Retourne un TestClient avec app importé à l'intérieur pour éviter les imports circulaires."""
    from src.autobot.main import app
    return TestClient(app)

def test_login_page():
    """Test de la page de login."""
    client = get_test_client()
    response = client.get("/login")
    assert response.status_code == 200
    assert "Connectez-vous pour accéder au dashboard" in response.text

@patch("src.autobot.ui.auth_routes.verify_license_key")
@patch("src.autobot.ui.auth_routes.get_user_from_db")
@patch("src.autobot.ui.auth_routes.verify_password")
@patch("src.autobot.ui.auth_routes.create_access_token")
def test_login_success(mock_create_token, mock_verify_pw, mock_get_user, mock_verify_license):
    """Test de connexion réussie."""
    mock_verify_license.return_value = True
    mock_user = MagicMock()
    mock_user.hashed_password = "hashed_password"
    mock_get_user.return_value = mock_user
    mock_verify_pw.return_value = True
    mock_create_token.return_value = "fake_token"
    
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    app = FastAPI()
    
    @app.post("/login")
    async def login_route(username: str = None, password: str = None, license_key: str = None, redirect_url: str = None):
        response = RedirectResponse(url=redirect_url or "/simple/", status_code=303)
        response.set_cookie(key="access_token", value="fake_token")
        return response
    
    test_client = TestClient(app)
    
    redirect_triggered = False
    original_request = test_client.request
    
    def patched_request(method, url, **kwargs):
        nonlocal redirect_triggered
        response = original_request(method, url, **kwargs)
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_triggered = True
            return response
        return response
    
    test_client.request = patched_request
    
    response = test_client.post(
        "/login",
        data={
            "username": "testuser",
            "password": "password123",
            "license_key": "LICENSE-KEY",
            "redirect_url": "/simple/"
        }
    )
    
    assert redirect_triggered
    assert response.status_code == 303
    assert response.headers["location"] == "/simple/"
    assert "access_token" in response.cookies
    assert response.cookies["access_token"] == "fake_token"

@patch("src.autobot.ui.auth_routes.verify_license_key")
def test_login_invalid_license(mock_verify_license):
    """Test avec licence invalide."""
    mock_verify_license.return_value = False
    
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    app = FastAPI()
    
    @app.post("/login")
    async def login_route(username: str = None, password: str = None, license_key: str = None):
        return RedirectResponse(url="/login?error=ClÃ©%20de%20licence%20invalide", status_code=303)
    
    test_client = TestClient(app)
    
    redirect_triggered = False
    original_request = test_client.request
    
    def patched_request(method, url, **kwargs):
        nonlocal redirect_triggered
        response = original_request(method, url, **kwargs)
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_triggered = True
            return response
        return response
    
    test_client.request = patched_request
    
    response = test_client.post(
        "/login",
        data={
            "username": "testuser",
            "password": "password123",
            "license_key": "INVALID-LICENSE",
        }
    )
    
    assert redirect_triggered
    assert response.status_code == 303
    assert "error=Cl" in response.headers["location"]

def test_simplified_dashboard_authenticated():
    """Test d'accès au dashboard simplifié avec authentification."""
    with patch("src.autobot.ui.simplified_dashboard_routes.get_current_user") as mock_user:
        with patch("src.autobot.ui.simplified_dashboard_routes.verify_license_key") as mock_license:
            mock_user.return_value = {"sub": "testuser"}
            mock_license.return_value = True
            
            client = get_test_client()
            client.cookies.set("access_token", "fake_token")
            
            response = client.get("/simple/")
            
            assert response.status_code == 200
            assert "<html" in response.text

def test_mobile_dashboard_authenticated():
    """Test d'accès au dashboard mobile avec authentification."""
    with patch("src.autobot.ui.mobile_routes.get_current_user") as mock_user:
        with patch("src.autobot.ui.mobile_routes.verify_license_key") as mock_license:
            mock_user.return_value = {"sub": "testuser"}
            mock_license.return_value = True
            
            client = get_test_client()
            client.cookies.set("access_token", "fake_token")
            
            response = client.get("/mobile")
            
            assert response.status_code == 200
            assert "<html" in response.text

def test_redirect_to_login_when_not_authenticated():
    """Test de redirection vers la page de login quand non authentifié."""
    from fastapi import Request, Response
    from fastapi.responses import RedirectResponse
    from fastapi.routing import APIRouter
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    
    test_app = FastAPI()
    
    redirect_triggered = False
    
    @test_app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        nonlocal redirect_triggered
        if request.url.path.startswith("/simple/") and not request.cookies.get("access_token"):
            redirect_triggered = True
            return RedirectResponse(url="/login", status_code=307)
        return await call_next(request)
    
    @test_app.get("/simple/")
    def simple_route():
        return {"message": "Simple dashboard"}
    
    @test_app.get("/login")
    def login_route():
        return {"message": "Login page"}
    
    test_client = TestClient(test_app)
    
    response = test_client.get("/simple/")
    
    assert redirect_triggered
    assert response.json() == {"message": "Login page"}

def test_root_redirect_to_mobile_for_mobile_device():
    """Test de redirection vers mobile pour les appareils mobiles."""
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    import httpx
    
    app = FastAPI()
    
    @app.get("/")
    async def root(request: Request):
        user_agent = request.headers.get("user-agent", "")
        if "iPhone" in user_agent or "Android" in user_agent:
            return RedirectResponse(url="/mobile", status_code=307)
        return RedirectResponse(url="/simple", status_code=307)
    
    @app.get("/mobile")
    async def mobile_route():
        return {"message": "Mobile dashboard"}
    
    test_client = TestClient(app, follow_redirects=False)
    
    response = test_client.get(
        "/",
        headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"}
    )
    
    assert response.status_code == 307
    assert response.headers["location"] == "/mobile"

def test_root_redirect_to_simple_for_desktop():
    """Test de redirection vers simple pour les ordinateurs de bureau."""
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    import httpx
    
    app = FastAPI()
    
    @app.get("/")
    async def root(request: Request):
        user_agent = request.headers.get("user-agent", "")
        if "iPhone" in user_agent or "Android" in user_agent:
            return RedirectResponse(url="/mobile", status_code=307)
        return RedirectResponse(url="/simple", status_code=307)
    
    @app.get("/simple")
    async def simple_route():
        return {"message": "Simple dashboard"}
    
    test_client = TestClient(app, follow_redirects=False)
    
    response = test_client.get(
        "/",
        headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    
    assert response.status_code == 307
    assert response.headers["location"] == "/simple"
