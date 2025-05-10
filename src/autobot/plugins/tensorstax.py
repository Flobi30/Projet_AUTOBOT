# File: src\autobot\plugins/tensorstax.py
# GENERATED_PLUGIN for agent "TensorStax" (category: Data Science)
import os
import requests

def get_data():
    """
    Stub for agent 'TensorStax'.
    Fetches from: https://api.example.com/tensorstax
    """
    headers = {}
    key = os.getenv("TENSORSTAX_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/tensorstax", headers=headers)
    resp.raise_for_status()
    return resp.json()
