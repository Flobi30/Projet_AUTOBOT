# File: src\autobot\plugins/bob.py
# GENERATED_PLUGIN for agent "Bob" (category: Digital Workers)
import os
import requests

def get_data():
    """
    Stub for agent 'Bob'.
    Fetches from: https://api.example.com/bob
    """
    headers = {}
    key = os.getenv("BOB_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/bob", headers=headers)
    resp.raise_for_status()
    return resp.json()
