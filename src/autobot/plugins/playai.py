# File: src\autobot\plugins/playai.py
# GENERATED_PLUGIN for agent "PlayAI" (category: Voice AI Agents)
import os
import requests

def get_data():
    """
    Stub for agent 'PlayAI'.
    Fetches from: https://api.example.com/playai
    """
    headers = {}
    key = os.getenv("PLAYAI_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/playai", headers=headers)
    resp.raise_for_status()
    return resp.json()
