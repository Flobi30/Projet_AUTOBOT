import requests

URL = "https://example.com"
resp = requests.get(URL)
print("Status:", resp.status_code)
data = resp.json()
# Affiche les clés de haut niveau et le nombre d'agents dans la première catégorie
print(data.keys())
print("Agents dans la 1ère catégorie :", len(data["categories"][0]["agents"]))
