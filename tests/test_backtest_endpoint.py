from fastapi.testclient import TestClient
from autobot.main import app

client = TestClient(app)

def test_backtest_endpoint():
    payload = { "strategy": "mean_reversion", "parameters": { "window": 14 } }
    response = client.post("/backtest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "mean_reversion"
    assert isinstance(data["metrics"], dict)
    for value in data["metrics"].values():
        assert isinstance(value, float)
