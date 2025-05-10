# File: src\autobot\plugins/shipstation.py
# GENERATED_PLUGIN for agent "Shipstation" (category: Content Creation)
import os
import requests

def get_data():
    """
    Stub for agent 'Shipstation'.
    Fetches from: https://api.example.com/shipstation
    """
    headers = {}
    key = os.getenv("SHIPSTATION_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/shipstation", headers=headers)
    resp.raise_for_status()
    return resp.json()
