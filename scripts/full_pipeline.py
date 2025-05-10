#!/usr/bin/env python3
"""
Full Autobot IA Agents Pipeline
- Fetch agents from API
- Score and deduplicate
- Shortlist top agents
- Save shortlist JSON
- Generate stub Python plugins
"""

import requests
import json
import os
import re
import argparse
from collections import defaultdict

# Optional OpenAI import for GPT-based scoring
try:
    import openai
except ImportError:
    openai = None

# Constants
API_URL = "https://backend-service-rnkajyidva-ue.a.run.app/api/categories/with-agents"
SHORTLIST_FILE = "agents_shortlist.json"
PLUGINS_DIR = os.path.join("src", "autobot", "plugins")

def fetch_agents():
    """Fetch and flatten all agents from the categories API."""
    resp = requests.get(API_URL)
    resp.raise_for_status()
    categories = resp.json()
    agents = []
    for cat in categories:
        for ag in cat.get("agents", []):
            agents.append({
                "id":               ag.get("_id"),
                "name":             ag.get("name"),
                "category":         cat.get("name"),
                "tags":             ag.get("tags", []),
                "popularityScore":  ag.get("popularityScore", {}).get("score", 0),
                "upvotes":          ag.get("upvotes", 0),
                "featured":         ag.get("featured", False),
            })
    return agents

def jaccard(a, b):
    """Compute Jaccard similarity between two lists."""
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)

def gpt_relevance(agent):
    """Optional GPT-based relevance scoring 1–5."""
    if openai is None:
        return 0.0
    prompt = f"""
You are an expert in trading, e-commerce and automation.
Rate the relevance of this AI agent for the Autobot project on a scale from 1 to 5.
Agent name: {agent['name']}
Category: {agent['category']}
Popularity score: {agent['popularityScore']}
Upvotes: {agent['upvotes']}
Tags: {', '.join(agent['tags'])}
Respond with just the number.
"""
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    text = resp.choices[0].message.content.strip()
    m = re.search(r"[1-5]", text)
    return float(m.group(0)) if m else 0.0

def score_agent(agent, use_gpt=False):
    """Global score = popularity + 0.1*upvotes + featured bonus + optional GPT score."""
    score = agent["popularityScore"] + 0.1 * agent["upvotes"]
    if agent["featured"]:
        score += 5
    if use_gpt:
        score += gpt_relevance(agent)
    return score

def shortlist(agents, top_n, use_gpt=False):
    """Score, sort, dedupe by tag similarity, and return top_n agents."""
    scored = [(agent, score_agent(agent, use_gpt)) for agent in agents]
    scored.sort(key=lambda x: x[1], reverse=True)
    final = []
    for agent, sc in scored:
        if len(final) >= top_n:
            break
        # ensure agent is not too similar to any already chosen
        if all(jaccard(agent['tags'], ex['tags']) < 0.5 for ex in final):
            final.append(agent)
    return final

def save_shortlist(agents, path=SHORTLIST_FILE):
    """Write shortlist to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)
    print(f"✅ Shortlist saved to {path}")

def snake_case(name):
    """Convert name to snake_case module name."""
    return re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")

def generate_stubs(shortlist, plugins_dir=PLUGINS_DIR):
    """Generate stub Python plugin for each agent in shortlist."""
    os.makedirs(plugins_dir, exist_ok=True)
    for agent in shortlist:
        mod = snake_case(agent['name'])
        fname = f"{mod}.py"
        path = os.path.join(plugins_dir, fname)
        if os.path.exists(path):
            print(f"⏭ Skipping existing stub {fname}")
            continue
        url = agent.get('url', f"https://api.example.com/{mod}")
        env_var = f"{mod.upper()}_KEY"
        content = f'''# File: {plugins_dir}/{fname}
# GENERATED_PLUGIN for agent "{agent['name']}" (category: {agent['category']})
import os
import requests

def get_data():
    """
    Stub for agent '{agent['name']}'.
    Fetches from: {url}
    """
    headers = {{}}
    key = os.getenv("{env_var}")
    if key:
        headers["Authorization"] = f"Bearer {{key}}"
    resp = requests.get("{url}", headers=headers)
    resp.raise_for_status()
    return resp.json()
'''
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✔️  Stub generated: {fname}")

def main():
    parser = argparse.ArgumentParser(description="Full Autobot Agents Pipeline")
    parser.add_argument("--top-n", type=int, default=30, help="Number of agents to shortlist")
    parser.add_argument("--use-gpt", action="store_true", help="Enable GPT-based relevance scoring")
    args = parser.parse_args()

    print("🔍 Fetching agents...")
    agents = fetch_agents()
    print(f"→ {len(agents)} agents fetched.")

    print("✂️  Shortlisting...")
    top_agents = shortlist(agents, top_n=args.top_n, use_gpt=args.use_gpt)
    save_shortlist(top_agents)

    print("🛠️ Generating plugin stubs...")
    generate_stubs(top_agents)
    print("✅ All done.")

if __name__ == "__main__":
    main()
