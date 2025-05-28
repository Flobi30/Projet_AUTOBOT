# File: src\autobot\plugins/vessium.py
# GENERATED_PLUGIN for agent "Vessium" (category: AI Agents Platform)
import os
import requests

def get_data():
    """
    Stub for agent 'Vessium'.
    Fetches from: https://api.example.com/vessium
    """
    headers = {}
    key = os.getenv("VESSIUM_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/vessium", headers=headers)
    resp.raise_for_status()
    return resp.json()
