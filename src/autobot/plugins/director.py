# File: src\autobot\plugins/director.py
# GENERATED_PLUGIN for agent "Director" (category: AI Video Agents)
import os
import requests

def get_data():
    """
    Stub for agent 'Director'.
    Fetches from: https://api.example.com/director
    """
    headers = {}
    key = os.getenv("DIRECTOR_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/director", headers=headers)
    resp.raise_for_status()
    return resp.json()
