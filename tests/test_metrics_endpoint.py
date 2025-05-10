from fastapi.testclient import TestClient
from autobot.main import app

client = TestClient(app)

def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_sales" in data
    assert "conversion_rate" in data
    assert "avg_order_value" in data
    assert isinstance(data["total_sales"], (int, float))
    assert isinstance(data["conversion_rate"], (int, float))
    assert isinstance(data["avg_order_value"], (int, float))
