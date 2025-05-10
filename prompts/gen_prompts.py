"""
GEN_PROMPTS - Génère tous les fichiers attendus listés dans prompts_index.json.
Appelle GPT-Code ou un moteur de génération à la volée selon les prompts stockés dans prompts/_archive.
"""

import json
import os

PROMPT_DIR = "Projet_AUTOBOT/prompts/_archive"
INDEX_PATH = "prompts/prompts_index.json"

def main():
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        prompts = json.load(f)

    for entry in prompts:
        print(f"📌 Prompt: {entry['prompt']}")
        print(f"➡️  Module: {entry['module']}")
        print(f"📁 Fichiers à générer :")
        for out in entry['outputs']:
            print(f"   - {out}")
        print("---")

    print("👉 Lancer GPT-Code ou Open Interpreter pour exploiter chaque prompt .md dans prompts/_archive")

if __name__ == "__main__":
    main()

