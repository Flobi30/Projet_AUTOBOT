# File: src\autobot\plugins/confident_ai.py
# GENERATED_PLUGIN for agent "Confident AI" (category: Observability)
import os
import requests

def get_data():
    """
    Stub for agent 'Confident AI'.
    Fetches from: https://api.example.com/confident_ai
    """
    headers = {}
    key = os.getenv("CONFIDENT_AI_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/confident_ai", headers=headers)
    resp.raise_for_status()
    return resp.json()
