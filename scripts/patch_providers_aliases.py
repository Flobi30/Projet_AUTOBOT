#!/usr/bin/env python3
"""
scripts/patch_providers_aliases.py

Patch automatique des fichiers providers pour y ajouter
les alias attendus par router.py (ex. get_intraday, get_time_series, get_shopify, etc.).
Usage (depuis la racine du projet) :
    python scripts/patch_providers_aliases.py
"""

import re
from pathlib import Path
from collections import defaultdict

# 1. Définition des chemins
ROOT          = Path(__file__).parent.parent
PROVIDERS_DIR = ROOT / "src" / "autobot" / "providers"
ROUTER_FILE   = ROOT / "src" / "autobot" / "router.py"

# 2. Lecture de router.py pour extraire les imports de providers
router_txt = ROUTER_FILE.read_text(encoding="utf-8")
mod_to_funcs = defaultdict(list)
pattern = re.compile(r"from\s+autobot\.providers\.(\w+)\s+import\s+(.+)")

for line in router_txt.splitlines():
    m = pattern.match(line.strip())
    if not m:
        continue
    module, imports = m.groups()
    for part in imports.split(","):
        part = part.strip()
        if " as " in part:
            func, alias = [p.strip() for p in part.split(" as ")]
        else:
            func = alias = part
        mod_to_funcs[module].append((func, alias))

# 3. Pour chaque module, on patch automatiquement les alias manquants
for module, funcs in mod_to_funcs.items():
    provider_py = PROVIDERS_DIR / f"{module}.py"
    if not provider_py.exists():
        print(f"⚠️  Module '{module}.py' introuvable, saut.")
        continue

    content = provider_py.read_text(encoding="utf-8")
    lines   = content.splitlines()
    to_add  = []

    for func, alias in funcs:
        # Vérifier que la fonction d'origine existe
        if not re.search(rf"^def\s+{func}\s*\(", content, flags=re.MULTILINE):
            print(f"   ⚠️  Fonction '{func}' introuvable dans {module}.py")
            continue
        # Si alias différent et non déjà déclaré, on planifie de l'ajouter
        alias_pattern = rf"^ {alias}\s*="
        if alias != func and not re.search(rf"^{alias}\s*=", content, flags=re.MULTILINE):
            to_add.append((func, alias))

    if to_add:
        with open(provider_py, "a", encoding="utf-8") as f:
            f.write("\n\n# --- Aliases ajoutés automatiquement par patch_providers_aliases.py\n")
