# File: src\autobot\plugins/manus_ai.py
# GENERATED_PLUGIN for agent "Manus AI" (category: Productivity)
import os
import requests

def get_data():
    """
    Stub for agent 'Manus AI'.
    Fetches from: https://api.example.com/manus_ai
    """
    headers = {}
    key = os.getenv("MANUS_AI_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/manus_ai", headers=headers)
    resp.raise_for_status()
    return resp.json()
