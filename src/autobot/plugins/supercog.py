# File: src\autobot\plugins/supercog.py
# GENERATED_PLUGIN for agent "Supercog" (category: Productivity)
import os
import requests

def get_data():
    """
    Stub for agent 'Supercog'.
    Fetches from: https://api.example.com/supercog
    """
    headers = {}
    key = os.getenv("SUPERCOG_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/supercog", headers=headers)
    resp.raise_for_status()
    return resp.json()
