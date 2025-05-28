"""
AUTOBOT AUDIT SCRIPT
Ce script scanne la structure du projet local et génère :
- audit_report.json : état des fichiers attendus
- actions_to_take.txt : instructions lisibles par GPT-Code pour compléter le projet
"""

import os
import json

BASE_DIR = "Projet_AUTOBOT"
REQUIRED_FILES = {
    "src": [
        "main.py", "autobot.py", "strategies.py", "backtester.py",
        "simulator.py", "portfolio.py", "logger.py", "config.py", "data_loader.py",
        "autobot_guardian.py", "social_sentiment.py"
    ],
    "tests": [
        "test_backtester.py", "test_simulator.py", "test_portfolio.py", "test_guardian.py"
    ],
    "scripts": [
        "gen_prompts.py", "discover_apis.py", "discover_agents.py",
        "cleanup_code.py", "cleanup_scaffolds.py", "generate_all.py"
    ],
    "scaffolds": [
        "ecommerce_scaffold.py", "dropshipping_scaffold.py", "nft_scaffold.py"
    ],
    "k8s": [
        "deployment.yaml", "service.yaml", "hpa.yaml"
    ],
    ".github/workflows": [
        "ci.yml"
    ]
}

report = {}

for folder, files in REQUIRED_FILES.items():
    full_folder_path = os.path.join(BASE_DIR, folder)
    report[folder] = {}
    for file in files:
        file_path = os.path.join(full_folder_path, file)
        report[folder][file] = "✅ exists" if os.path.isfile(file_path) else "❌ missing"

# Sauvegarder audit_report.json
with open("audit_report.json", "w") as f:
    json.dump(report, f, indent=2)

# Générer actions_to_take.txt
with open("actions_to_take.txt", "w") as f:
    f.write("# ACTIONS À EFFECTUER POUR COMPLÉTER LE PROJET AUTOBOT\n\n")
    for folder in report:
        for file, status in report[folder].items():
            if "missing" in status:
                f.write(f"- Créer {folder}/{file}\n")

print("✅ Audit terminé. Fichiers générés : audit_report.json, actions_to_take.txt")

