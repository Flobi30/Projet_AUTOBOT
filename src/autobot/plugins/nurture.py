# File: src\autobot\plugins/nurture.py
# GENERATED_PLUGIN for agent "Nurture" (category: Productivity)
import os
import requests

def get_data():
    """
    Stub for agent 'Nurture'.
    Fetches from: https://api.example.com/nurture
    """
    headers = {}
    key = os.getenv("NURTURE_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/nurture", headers=headers)
    resp.raise_for_status()
    return resp.json()
