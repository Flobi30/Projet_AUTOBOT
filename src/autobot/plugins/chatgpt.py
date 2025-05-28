# File: src\autobot\plugins/chatgpt.py
# GENERATED_PLUGIN for agent "ChatGPT" (category: Personal Assistant)
import os
import requests

def get_data():
    """
    Stub for agent 'ChatGPT'.
    Fetches from: https://api.example.com/chatgpt
    """
    headers = {}
    key = os.getenv("CHATGPT_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/chatgpt", headers=headers)
    resp.raise_for_status()
    return resp.json()
