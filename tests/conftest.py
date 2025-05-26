# tests/conftest.py
import sys, os
import logging
from unittest.mock import MagicMock, patch

# calcul du chemin absolu vers le dossier src/
root = os.path.dirname(os.path.dirname(__file__))
src  = os.path.join(root, "src")

# ajoute src/ en fin de sys.path pour que pytest voit le package
if src not in sys.path:
    sys.path.append(src)

os.environ["PYTEST_CURRENT_TEST"] = "True"

# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from src.autobot.main import app

# Import thread cleanup fixture to ensure all threads are properly terminated
# The fixture is automatically used due to autouse=True
from thread_cleanup import thread_cleanup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

mock_get_current_user = MagicMock(return_value={"sub": "testuser"})
mock_verify_license_key = MagicMock(return_value=True)

sys.modules['src.autobot.ui.dashboard_routes.get_current_user'] = mock_get_current_user
sys.modules['src.autobot.ui.dashboard_routes.verify_license_key'] = mock_verify_license_key
sys.modules['src.autobot.ui.mobile_routes.get_current_user'] = mock_get_current_user
sys.modules['src.autobot.ui.mobile_routes.verify_license_key'] = mock_verify_license_key

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure l'environnement de test avec les mocks nécessaires."""
    with patch('src.autobot.ui.dashboard_routes.get_current_user', return_value={"sub": "testuser"}):
        with patch('src.autobot.ui.dashboard_routes.verify_license_key', return_value=True):
            with patch('src.autobot.ui.mobile_routes.get_current_user', return_value={"sub": "testuser"}):
                with patch('src.autobot.ui.mobile_routes.verify_license_key', return_value=True):
                    yield

@pytest.fixture(scope="session")
def client():
    """
    Fournit un TestClient pointé sur votre app FastAPI,
    utilisable dans tous les tests d'endpoint.
    """
    with TestClient(app) as test_client:
        test_client.cookies.set("access_token", "fake_token")
        yield test_client

import asyncio
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

class MockUser:
    def __init__(self, id="test_user", username="test", role="user"):
        self.id = id
        self.username = username
        self.role = role

async def mock_get_current_user_ws(websocket: WebSocket):
    """Version simplifiée de get_current_user_ws pour les tests"""
    return MockUser()

if 'pytest' in sys.modules:
    sys.modules['autobot.autobot_security.auth.user_manager'].get_current_user_ws = mock_get_current_user_ws
    
    try:
        import src.autobot.ui.dashboard_routes
        import src.autobot.ui.mobile_routes
        
        src.autobot.ui.dashboard_routes.get_current_user = mock_get_current_user
        src.autobot.ui.dashboard_routes.verify_license_key = mock_verify_license_key
        src.autobot.ui.mobile_routes.get_current_user = mock_get_current_user
        src.autobot.ui.mobile_routes.verify_license_key = mock_verify_license_key
    except ImportError as e:
        print(f"Warning: Could not patch UI routes: {e}")
