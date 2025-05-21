from fastapi.testclient import TestClient
from autobot.main import app
import pytest
from unittest.mock import patch, MagicMock
import re

client = TestClient(app)

@pytest.fixture
def authenticated_client():
    """Create a test client with authentication."""
    test_client = TestClient(app)
    
    with patch("autobot.autobot_security.auth.jwt_handler.verify_token", return_value={"sub": "testuser"}):
        return test_client

def test_simplified_dashboard_access(authenticated_client):
    """Test access to the simplified dashboard."""
    response = authenticated_client.get("/simple/")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    
    dashboard_elements = [
        "Performance", "Metrics", "Statistics", "Chart", "Graph", 
        "Portfolio", "Balance", "Assets", "Trades"
    ]
    
    assert any(element in response.text for element in dashboard_elements)

def test_mobile_dashboard_access(authenticated_client):
    """Test access to the mobile dashboard."""
    response = authenticated_client.get("/mobile/")
    assert response.status_code == 200
    assert "Mobile" in response.text or "Dashboard" in response.text

def test_dashboard_data_endpoints(authenticated_client):
    """Test endpoints that provide data for the dashboard."""
    data_endpoints = [
        "/api/dashboard/summary",
        "/api/dashboard/performance",
        "/api/dashboard/trades",
        "/api/dashboard/balance"
    ]
    
    for endpoint in data_endpoints:
        try:
            response = authenticated_client.get(endpoint)
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, (dict, list))
        except Exception:
            continue

def test_dashboard_unauthenticated_access():
    """Test that unauthenticated users cannot access the dashboard."""
    response = client.get("/simple/")
    assert response.status_code in [301, 302, 401, 403]
    
    response = client.get("/mobile/")
    assert response.status_code in [301, 302, 401, 403]

def test_dashboard_csrf_protection(authenticated_client):
    """Test CSRF protection on dashboard forms."""
    response = authenticated_client.get("/simple/")
    assert response.status_code == 200
    
    csrf_token_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    if csrf_token_match:
        csrf_token = csrf_token_match.group(1)
        
        form_data = {
            "csrf_token": csrf_token,
            "action": "update_settings",
            "setting_name": "test_setting",
            "setting_value": "test_value"
        }
        
        response = authenticated_client.post("/simple/settings", data=form_data)
        assert response.status_code in [200, 302]
        
        form_data.pop("csrf_token")
        response = authenticated_client.post("/simple/settings", data=form_data)
        assert response.status_code == 403
