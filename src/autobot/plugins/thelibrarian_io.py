# File: src\autobot\plugins/thelibrarian_io.py
# GENERATED_PLUGIN for agent "TheLibrarian.io" (category: Productivity)
import os
import requests

def get_data():
    """
    Stub for agent 'TheLibrarian.io'.
    Fetches from: https://api.example.com/thelibrarian_io
    """
    headers = {}
    key = os.getenv("THELIBRARIAN_IO_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/thelibrarian_io", headers=headers)
    resp.raise_for_status()
    return resp.json()
