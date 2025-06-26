# File: src\autobot\plugins/xagent.py
# GENERATED_PLUGIN for agent "XAgent" (category: Digital Workers)
import os
import requests

def get_data():
    """
    Stub for agent 'XAgent'.
    Fetches from: https://api.example.com/xagent
    """
    headers = {}
    key = os.getenv("XAGENT_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/xagent", headers=headers)
    resp.raise_for_status()
    return resp.json()
