import requests
from bs4 import BeautifulSoup
import json

url = "https://aiagentsdirectory.com/"
resp = requests.get(url)
soup = BeautifulSoup(resp.text, "html.parser")

agents = []
# Adapt selector si ncessaire : ici on prend tous les liens d'agent
for card in soup.select(".agent-card"):
    name = card.select_one(".agent-name").get_text(strip=True)
    desc = card.select_one(".agent-description").get_text(strip=True)
    link = card.select_one("a")["href"]
    agents.append({"name": name, "description": desc, "url": link})

with open("agents_manifest.json", "w", encoding="utf-8") as f:
    json.dump(agents, f, indent=2)

print(f"Discovered {len(agents)} agents")

