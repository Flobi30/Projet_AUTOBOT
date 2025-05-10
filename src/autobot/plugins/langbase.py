# File: src\autobot\plugins/langbase.py
# GENERATED_PLUGIN for agent "Langbase" (category: AI Agents Platform)
import os
import requests

def get_data():
    """
    Stub for agent 'Langbase'.
    Fetches from: https://api.example.com/langbase
    """
    headers = {}
    key = os.getenv("LANGBASE_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/langbase", headers=headers)
    resp.raise_for_status()
    return resp.json()
