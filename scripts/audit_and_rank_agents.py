# File: scripts/audit_and_rank_agents.py
import requests
import json
from collections import defaultdict

# 1) URL de l’API qui renvoie toutes les catégories + agents
API_URL = "https://backend-service-rnkajyidva-ue.a.run.app/api/categories/with-agents"

# 2) Tes compétences clés
REQUIRED_CAPABILITIES = [
    "Trading",
    "Market Data",
    "E-Commerce",
    "Automation",
    "Research",
    "Risk Management",
    "RL Training",
]

def fetch_agents():
    """Récupère tous les agents et les aplatit en une liste."""
    resp = requests.get(API_URL)
    resp.raise_for_status()
    categories = resp.json()  # liste de dict {name, agents: […]}
    agents = []
    for cat in categories:
        for ag in cat.get("agents", []):
            agents.append({
                "id":               ag.get("_id"),
                "name":             ag.get("name"),
                "category":         cat.get("name"),
                "popularityScore":  ag.get("popularityScore", {}).get("score", 0),
                "upvotes":          ag.get("upvotes", 0),
                "featured":         ag.get("featured", False),
            })
    return agents

def shortlist_by_capabilities(agents, top_n=3):
    """Pour chaque compétence, prend les top_n agents."""
    buckets = defaultdict(list)
    for ag in agents:
        buckets[ag["category"]].append(ag)

    final = []
    for cap in REQUIRED_CAPABILITIES:
        group = sorted(
            buckets.get(cap, []),
            key=lambda a: a["popularityScore"] + 0.1*a["upvotes"],
            reverse=True
        )
        final.extend(group[:top_n])
    # dé-duplication
    seen = set(); uniq = []
    for a in final:
        if a["id"] not in seen:
            seen.add(a["id"])
            uniq.append(a)
    return uniq

def save_shortlist(shortlist, path="agents_shortlist.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(shortlist, f, indent=2, ensure_ascii=False)

def main():
    print("🔍 Extraction des agents…")
    agents = fetch_agents()
    print(f"→ {len(agents)} agents extraits.")

    print("✂️  Shortlisting par compétence…")
    top = shortlist_by_capabilities(agents, top_n=3)
    save_shortlist(top)
    print(f"✅ agents_shortlist.json généré avec {len(top)} agents.")

if __name__ == "__main__":
    main()
