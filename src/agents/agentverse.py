# File: src\autobot\plugins/agentverse.py
# GENERATED_PLUGIN for agent "Agentverse" (category: AI Agents Platform)
import os
import requests

def get_data():
    """
    Stub for agent 'Agentverse'.
    Fetches from: https://api.example.com/agentverse
    """
    headers = {}
    key = os.getenv("AGENTVERSE_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/agentverse", headers=headers)
    resp.raise_for_status()
    return resp.json()
