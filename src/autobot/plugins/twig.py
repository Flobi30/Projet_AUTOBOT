# File: src\autobot\plugins/twig.py
# GENERATED_PLUGIN for agent "Twig" (category: Customer Service)
import os
import requests

def get_data():
    """
    Stub for agent 'Twig'.
    Fetches from: https://api.example.com/twig
    """
    headers = {}
    key = os.getenv("TWIG_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/twig", headers=headers)
    resp.raise_for_status()
    return resp.json()
