# File: src\autobot\plugins/garnit.py
# GENERATED_PLUGIN for agent "Garnit" (category: Email AI Agents)
import os
import requests

def get_data():
    """
    Stub for agent 'Garnit'.
    Fetches from: https://api.example.com/garnit
    """
    headers = {}
    key = os.getenv("GARNIT_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/garnit", headers=headers)
    resp.raise_for_status()
    return resp.json()
