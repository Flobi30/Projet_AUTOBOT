from fastapi.testclient import TestClient
from autobot.main import app
import pytest
from unittest.mock import patch, MagicMock

client = TestClient(app)

def test_get_backtest_endpoint():
    """Test the GET /backtest endpoint with a valid symbol parameter."""
    response = client.get("/backtest?symbol=BTC/USDT")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)

def test_get_backtest_endpoint_missing_symbol():
    """Test the GET /backtest endpoint without a symbol parameter."""
    response = client.get("/backtest")
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data

def test_get_backtest_endpoint_invalid_symbol():
    """Test the GET /backtest endpoint with an invalid symbol."""
    with patch("autobot.backtest_engine.run_backtest", side_effect=ValueError("Invalid symbol")):
        response = client.get("/backtest?symbol=INVALID")
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

def test_get_backtest_endpoint_with_parameters():
    """Test the GET /backtest endpoint with additional parameters."""
    response = client.get("/backtest?symbol=BTC/USDT&strategy=mean_reversion&timeframe=1h")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
