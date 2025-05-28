#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re

AGENT_LIST_URL = "https://aiagentsdirectory.com/agents"  # ou l’API si dispo

def fetch_agent_list():
    """
    Récupère la liste brute des agents depuis le site.
    """
    resp = requests.get(AGENT_LIST_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # Exemple : chaque agent est dans <div class="agent-card" data-json="...">
    agents = []
    for card in soup.select("div.agent-card"):
        data = card.get("data-json")
        if not data:
            continue
        info = json.loads(data)
        agents.append({
            "name":    info.get("title"),
            "tags":    info.get("tags", []),
            "desc":    info.get("description", ""),
            "url":     info.get("url"),
        })
    return agents

def score_agent(agent):
    """
    Donne un score basé sur la présence de mots‐clés 'API', 'finance', 'crypto', 'trading', etc.
    """
    text = (agent["name"] + " " + agent["desc"] + " " + " ".join(agent["tags"])).lower()
    score = 0
    for kw in ["api", "crypto", "trading", "finance", "data", "automation"]:
        if kw in text:
            score += 1
    return score

def shortlist(agents, top_n=10):
    """
    Trie par score et renvoie les top_n agents.
    """
    ranked = sorted(agents, key=lambda a: score_agent(a), reverse=True)
    return ranked[:top_n]

def main():
    agents = fetch_agent_list()
    top = shortlist(agents, top_n=20)
    # Sauvegarde dans un JSON, ou affiche en console
    with open("agents_shortlist.json", "w", encoding="utf-8") as f:
        json.dump(top, f, indent=2, ensure_ascii=False)
    print(f"🔍 Liste restreinte générée : agents_shortlist.json ({len(top)} agents)")

if __name__ == "__main__":
    main()
