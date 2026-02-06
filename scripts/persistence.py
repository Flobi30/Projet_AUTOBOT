#!/usr/bin/env python3
"""Module de persistance pour sauvegarder l'etat du bot."""

import json
import os
from datetime import datetime
from typing import Dict, Any, List

STATE_FILE = "bot_state.json"


def save_state(orders: List[Dict], positions: List[Dict], metrics: Dict) -> None:
    """Sauvegarde l'etat dans un fichier JSON."""
    state = {
        "last_update": datetime.now().isoformat(),
        "orders": orders,
        "positions": positions,
        "metrics": metrics,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_state() -> Dict[str, Any]:
    """Charge l'etat depuis le fichier JSON."""
    if not os.path.exists(STATE_FILE):
        return {"orders": [], "positions": [], "metrics": {}}
    with open(STATE_FILE, "r") as f:
        return json.load(f)
