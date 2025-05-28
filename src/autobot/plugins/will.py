# File: src\autobot\plugins/will.py
# GENERATED_PLUGIN for agent "Will" (category: Digital Workers)
import os
import requests

def get_data():
    """
    Stub for agent 'Will'.
    Fetches from: https://api.example.com/will
    """
    headers = {}
    key = os.getenv("WILL_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/will", headers=headers)
    resp.raise_for_status()
    return resp.json()
