import os, json

# Charge le manifest de projet
manifest = json.load(open("project_manifest.json", encoding="utf-8"))

# Template gnrique pour chaque module
template = """# prompts/{name}_scaffold.md

## System
You are a senior engineer. Scaffold the `{name}` module for AUTOBOT.

## User
Create a Python package `{name}/` that:
1. ...dcrire les fonctionnalits de base pour le module {name}
2. ...
3. ...

## Output
- Files under `src/{name}/`
- Tests under `tests/test_{name}.py`
- Documentation under `docs/{name}_guide.md`
"""

# Cre le dossier prompts s'il n'existe pas
os.makedirs("prompts", exist_ok=True)

# Pour chaque module du manifest, cre le prompt s'il n'existe pas
for mod in manifest["modules"]:
    filename = f"prompts/{mod}_scaffold.md"
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(template.format(name=mod))
        print("Created prompt", filename)
    else:
        print("Prompt exists", filename)

