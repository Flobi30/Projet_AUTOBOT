# File: src\autobot\plugins/qwen_chat.py
# GENERATED_PLUGIN for agent "Qwen Chat" (category: Personal Assistant)
import os
import requests

def get_data():
    """
    Stub for agent 'Qwen Chat'.
    Fetches from: https://api.example.com/qwen_chat
    """
    headers = {}
    key = os.getenv("QWEN_CHAT_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/qwen_chat", headers=headers)
    resp.raise_for_status()
    return resp.json()
