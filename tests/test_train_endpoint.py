from fastapi.testclient import TestClient
from autobot.main import app

client = TestClient(app)

def test_train_endpoint():
    response = client.post("/train")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "training_started"
    assert isinstance(data.get("job_id"), str)