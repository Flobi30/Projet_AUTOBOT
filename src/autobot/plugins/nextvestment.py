# File: src\autobot\plugins/nextvestment.py
# GENERATED_PLUGIN for agent "Nextvestment" (category: Productivity)
import os
import requests

def get_data():
    """
    Stub for agent 'Nextvestment'.
    Fetches from: https://api.example.com/nextvestment
    """
    headers = {}
    key = os.getenv("NEXTVESTMENT_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/nextvestment", headers=headers)
    resp.raise_for_status()
    return resp.json()
