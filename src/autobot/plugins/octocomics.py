# File: src\autobot\plugins/octocomics.py
# GENERATED_PLUGIN for agent "OctoComics" (category: Images)
import os
import requests

def get_data():
    """
    Stub for agent 'OctoComics'.
    Fetches from: https://api.example.com/octocomics
    """
    headers = {}
    key = os.getenv("OCTOCOMICS_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/octocomics", headers=headers)
    resp.raise_for_status()
    return resp.json()
