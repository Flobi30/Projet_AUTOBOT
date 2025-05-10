# tests/conftest.py
import sys, os

# calcul du chemin absolu vers le dossier src/
root = os.path.dirname(os.path.dirname(__file__))
src  = os.path.join(root, "src")

# ajoute src/ en fin de sys.path pour que pytest voit le package
if src not in sys.path:
    sys.path.append(src)

# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from autobot.main import app

@pytest.fixture(scope="session")
def client():
    """
    Fournit un TestClient pointé sur votre app FastAPI,
    utilisable dans tous les tests d’endpoint.
    """
    return TestClient(app)
