#!/usr/bin/env python3

import requests
import json
import sys

def test_api_endpoints():
    """Test the API endpoints for functionality"""
    base_url = "http://localhost:8000"
    
    api_data = {
        "api": {
            "alpha-vantage-api-key": "test_key",
            "newsapi-api-key": "test_key",
            "twelve-data-api-key": "test_key"
        }
    }
    
    try:
        response = requests.post(f"{base_url}/api/save-settings", json=api_data)
        print(f"API Save Test: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"API Save Test Failed: {e}")
    
    deposit_data = {"amount": 100, "method": "bank"}
    try:
        response = requests.post(f"{base_url}/api/deposit", json=deposit_data)
        print(f"Deposit Test: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Deposit Test Failed: {e}")
    
    withdraw_data = {"amount": 50, "method": "bank"}
    try:
        response = requests.post(f"{base_url}/api/withdraw", json=withdraw_data)
        print(f"Withdraw Test: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Withdraw Test Failed: {e}")

if __name__ == "__main__":
    test_api_endpoints()
