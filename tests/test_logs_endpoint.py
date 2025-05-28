from fastapi.testclient import TestClient
from autobot.main import app

client = TestClient(app)

def test_logs_endpoint():
    response = client.get("/logs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "timestamp" in first and "level" in first and "msg" in first