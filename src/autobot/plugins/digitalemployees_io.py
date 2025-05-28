# File: src\autobot\plugins/digitalemployees_io.py
# GENERATED_PLUGIN for agent "DigitalEmployees.io" (category: Digital Workers)
import os
import requests

def get_data():
    """
    Stub for agent 'DigitalEmployees.io'.
    Fetches from: https://api.example.com/digitalemployees_io
    """
    headers = {}
    key = os.getenv("DIGITALEMPLOYEES_IO_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.get("https://api.example.com/digitalemployees_io", headers=headers)
    resp.raise_for_status()
    return resp.json()
