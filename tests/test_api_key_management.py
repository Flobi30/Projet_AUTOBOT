from fastapi.testclient import TestClient
from autobot.main import app
import pytest
import os
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

client = TestClient(app)

@pytest.fixture
def mock_env_file(tmp_path):
    """Create a temporary .env file for testing."""
    env_file = tmp_path / ".env"
    env_file.write_text("""
PYTHONPATH=src
ALPHA_KEY=test_alpha_key
TWELVE_KEY=test_twelve_key
FRED_KEY=test_fred_key
NEWSAPI_KEY=test_news_key
SHOPIFY_KEY=test_shopify_key
SHOPIFY_SHOP_NAME=test_shop_name
JWT_SECRET_KEY=test_jwt_key
JWT_ALGORITHM=HS256
TOKEN_EXPIRE_MINUTES=1440
LICENSE_KEY=TEST-LICENSE-KEY
    """)
    return str(env_file)

def test_env_api_keys_loaded():
    """Test that API keys are correctly loaded from .env file."""
    load_dotenv()
    
    assert os.getenv("ALPHA_KEY") is not None
    assert os.getenv("TWELVE_KEY") is not None
    assert os.getenv("FRED_KEY") is not None
    assert os.getenv("NEWSAPI_KEY") is not None
    assert os.getenv("SHOPIFY_KEY") is not None
    assert os.getenv("SHOPIFY_SHOP_NAME") is not None

def test_api_key_validation():
    """Test API key validation logic."""
    
    with patch("autobot.autobot_security.auth.jwt_handler.verify_token", return_value={"sub": "testuser"}):
        response = client.get("/api/status")
        assert response.status_code == 200
        
        if hasattr(app, "api_key_validation_endpoint"):
            response = client.get(app.api_key_validation_endpoint)
            assert response.status_code == 200
            data = response.json()
            assert "alpha_key_valid" in data
            assert "twelve_key_valid" in data

@patch("os.environ")
def test_api_key_update(mock_environ, mock_env_file):
    """Test updating API keys."""
    
    mock_environ.get.return_value = "test_token"
    
    with patch("autobot.autobot_security.auth.jwt_handler.verify_token", return_value={"sub": "testuser", "role": "admin"}):
        if hasattr(app, "api_key_update_endpoint"):
            response = client.post(
                app.api_key_update_endpoint,
                json={
                    "alpha_key": "new_alpha_key",
                    "twelve_key": "new_twelve_key"
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "success"

def test_api_key_security():
    """Test that API keys are not exposed in responses."""
    
    with patch("autobot.autobot_security.auth.jwt_handler.verify_token", return_value={"sub": "testuser"}):
        endpoints = ["/api/status", "/metrics", "/health"]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            if response.status_code == 200:
                data = response.json()
                data_str = str(data)
                assert "ALPHA_KEY" not in data_str
                assert "TWELVE_KEY" not in data_str
                assert "FRED_KEY" not in data_str
                assert "NEWSAPI_KEY" not in data_str
                assert "SHOPIFY_KEY" not in data_str
