# File: src\autobot\plugins/doozerai.py
# GENERATED_PLUGIN for agent "DoozerAI" (category: Digital Workers)
import os
import requests

def get_data():
    """
    Stub for agent 'DoozerAI'.
    Fetches from: https://api.example.com/doozerai
    """
    headers = {}
    key = os.getenv("DOOZERAI_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/doozerai", headers=headers)
    resp.raise_for_status()
    return resp.json()
