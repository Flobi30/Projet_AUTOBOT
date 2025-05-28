# File: src\autobot\plugins/teammates_ai.py
# GENERATED_PLUGIN for agent "Teammates.ai" (category: Voice AI Agents)
import os
import requests

def get_data():
    """
    Stub for agent 'Teammates.ai'.
    Fetches from: https://api.example.com/teammates_ai
    """
    headers = {}
    key = os.getenv("TEAMMATES_AI_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/teammates_ai", headers=headers)
    resp.raise_for_status()
    return resp.json()
