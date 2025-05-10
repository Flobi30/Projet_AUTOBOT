import json, os, subprocess, re

def snake(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")

agents = json.load(open("agents_shortlist.json", encoding="utf-8"))
for agent in agents:
    mod = snake(agent["name"])
    prompt = f"""
Crée un module Python src/autobot/plugins/{mod}.py :
- Fonction get_data() qui fait un GET sur {agent['url']}.
- Ajoute un header Authorization Bearer ${{{mod.upper()}_KEY}} si nécessaire.
- Retourne la réponse JSON brute.
# GENERATED_PLUGIN
"""
    env = os.environ.copy()
    env["PROMPT_OVERRIDE"] = prompt
    subprocess.run(
        ["python", "scripts/assist_phase.py", f"add_{mod}_plugin"],
        check=True, env=env
    )
    print(f"🛠️ Plugin {mod} généré.")
