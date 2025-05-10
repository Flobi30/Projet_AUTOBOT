# tests/test_endpoints.py

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_predict_endpoint(client):
    response = client.get("/predict")
    assert response.status_code == 200

    data = response.json()
    # On s’attend à une clef "prediction" numérique
    assert "prediction" in data
    assert isinstance(data["prediction"], (int, float))
