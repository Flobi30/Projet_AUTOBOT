"""
AUTOBOT DEEP AUDIT SCRIPT
Ce script va :
1. Vérifier l'existence des fichiers clés.
2. Vérifier que les fichiers ne sont pas vides.
3. Scanner les fichiers pour détecter les fonctions attendues.
4. Vérifier l'importabilité sans erreur.
5. Générer un rapport détaillé.
"""

import os
import importlib.util
import ast
import json

BASE_DIR = "Projet_AUTOBOT"
REQUIRED_FILES = {
    "src": {
        "main.py": ["main"],
        "autobot.py": [],
        "strategies.py": [],
        "backtester.py": [],
        "simulator.py": [],
        "portfolio.py": [],
        "logger.py": [],
        "config.py": [],
        "data_loader.py": [],
        "autobot_guardian.py": [],
        "social_sentiment.py": []
    },
    "tests": {
        "test_backtester.py": [],
        "test_simulator.py": [],
        "test_portfolio.py": [],
        "test_guardian.py": []
    },
    "scripts": {
        "gen_prompts.py": [],
        "discover_apis.py": [],
        "discover_agents.py": [],
        "cleanup_code.py": [],
        "cleanup_scaffolds.py": [],
        "generate_all.py": []
    }
}

report = {}

def is_importable(file_path):
    try:
        spec = importlib.util.spec_from_file_location("module.name", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except Exception:
        return False

def scan_file_for_functions(file_path, expected_functions):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        return {fn: (fn in functions) for fn in expected_functions}
    except Exception:
        return {fn: False for fn in expected_functions}

for folder, files in REQUIRED_FILES.items():
    folder_path = os.path.join(BASE_DIR, folder)
    report[folder] = {}
    for filename, expected_fns in files.items():
        file_path = os.path.join(folder_path, filename)
        entry = {
            "exists": os.path.isfile(file_path),
            "size": 0,
            "empty": True,
            "importable": False,
            "functions": {}
        }
        if entry["exists"]:
            entry["size"] = os.path.getsize(file_path)
            entry["empty"] = entry["size"] == 0
            entry["importable"] = is_importable(file_path)
            if expected_fns:
                entry["functions"] = scan_file_for_functions(file_path, expected_fns)
        report[folder][filename] = entry

# Save the report
with open("deep_audit_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("✅ Audit profond terminé. Fichier généré : deep_audit_report.json")

