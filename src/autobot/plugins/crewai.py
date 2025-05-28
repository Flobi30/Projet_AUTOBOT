# File: src\autobot\plugins/crewai.py
# GENERATED_PLUGIN for agent "CrewAI" (category: AI Agents Frameworks)
import os
import requests

def get_data():
    """
    Stub for agent 'CrewAI'.
    Fetches from: https://api.example.com/crewai
    """
    headers = {}
    key = os.getenv("CREWAI_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/crewai", headers=headers)
    resp.raise_for_status()
    return resp.json()
