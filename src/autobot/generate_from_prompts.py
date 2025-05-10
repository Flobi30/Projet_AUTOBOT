"""
GENERATE_FROM_PROMPTS - VERSION CORRIGÉE
Génère tous les fichiers attendus depuis prompts_index.json,
en évitant les doublons et en corrigeant les erreurs fichier/dossier.

Nouvelles protections :
- Ignore les entrées qui n'ont pas d'extension de fichier
- Ignore les chemins déjà existants s’ils sont des fichiers bloquants
- Corrige automatiquement les erreurs FileExistsError
"""

import os
import json

PROMPT_DIR = "prompts/_archive"
INDEX_PATH = "prompts/prompts_index.json"
LOG_PATH = "prompts/generation_log.json"

def already_generated(log, path):
    return path in log.get("generated", [])

def log_generation(path, log):
    log.setdefault("generated", []).append(path)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

def generate_file(path, content):
    dir_path = os.path.dirname(path)
    if dir_path:
        try:
            os.makedirs(dir_path, exist_ok=True)
        except FileExistsError:
            print(f"⛔ Conflit : {dir_path} est un fichier, pas un dossier.")
            return
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            generation_log = json.load(f)
    else:
        generation_log = {"generated": []}

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    for entry in prompts:
        prompt_path = os.path.join(PROMPT_DIR, entry["prompt"])
        if not os.path.isfile(prompt_path):
            print(f"❌ Prompt manquant : {entry['prompt']}")
            continue

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()

        for output_path in entry["outputs"]:
            full_output_path = os.path.normpath(output_path)

            # Ignorer les chemins sans extension (probable dossier)
            if "." not in os.path.basename(full_output_path):
                print(f"🚫 Ignoré (pas un fichier) : {full_output_path}")
                continue

            if already_generated(generation_log, full_output_path):
                print(f"⚠️  Déjà généré (ignoré) : {full_output_path}")
                continue

            if os.path.exists(full_output_path):
                print(f"⛔ Fichier déjà présent : {full_output_path}")
                continue

            print(f"✅ Génération : {full_output_path}")
            generate_file(full_output_path, f"# Généré automatiquement depuis : {entry['prompt']}\n\n{prompt_content}")
            log_generation(full_output_path, generation_log)

    print("\n✅ Génération terminée. Consultez prompts/generation_log.json pour le suivi.")

if __name__ == "__main__":
    main()

