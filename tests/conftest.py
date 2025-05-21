# tests/conftest.py
import sys, os
import logging

# calcul du chemin absolu vers le dossier src/
root = os.path.dirname(os.path.dirname(__file__))
src  = os.path.join(root, "src")

# ajoute src/ en fin de sys.path pour que pytest voit le package
if src not in sys.path:
    sys.path.append(src)

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

@pytest.fixture(scope="session")
def client():
    """
    Fournit un TestClient pointé sur votre app FastAPI,
    utilisable dans tous les tests d'endpoint.
    """
    return TestClient(app)

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

import sys
if 'pytest' in sys.modules:
    sys.modules['autobot.autobot_security.auth.user_manager'].get_current_user_ws = mock_get_current_user_ws
