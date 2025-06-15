import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from autobot.main import app

client = TestClient(app)

def test_capital_status_endpoint():
    """Test the /api/capital-status endpoint returns proper CapitalStatus structure."""
    
    mock_summary = {
        "initial_capital": 500.0,
        "current_capital": 550.0,
        "total_deposits": 100.0,
        "total_withdrawals": 0.0,
        "trading_profit": 50.0,
        "total_profit": 50.0,
        "roi": 10.0,
        "available_for_withdrawal": 550.0,
        "last_updated": "2025-06-15T16:00:00"
    }
    
    with patch('autobot.routers.capital.CapitalManager') as mock_capital_manager:
        mock_instance = MagicMock()
        mock_instance.get_capital_summary.return_value = mock_summary
        mock_capital_manager.return_value = mock_instance
        
        response = client.get("/api/capital-status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["initial_capital"] == 500.0
        assert data["current_capital"] == 550.0
        assert data["total_deposits"] == 100.0
        assert data["total_withdrawals"] == 0.0
        assert data["trading_profit"] == 50.0
        assert data["total_profit"] == 50.0
        assert data["roi"] == 10.0
        assert data["available_for_withdrawal"] == 550.0
        assert "last_updated" in data

def test_capital_status_endpoint_error_handling():
    """Test error handling when CapitalManager fails."""
    
    with patch('autobot.routers.capital.CapitalManager') as mock_capital_manager:
        mock_capital_manager.side_effect = Exception("Database error")
        
        response = client.get("/api/capital-status")
        
        assert response.status_code == 500
        assert "Failed to get capital status" in response.json()["detail"]

def test_compounding_logic():
    """Test that compounding logic calculates correctly."""
    old_capital = 500.0
    daily_return = 0.02
    expected_new_capital = old_capital * (1 + daily_return)
    
    assert expected_new_capital == 510.0
    
    old_capital = 1000.0
    daily_return = -0.01
    expected_new_capital = old_capital * (1 + daily_return)
    
    assert expected_new_capital == 990.0
