#!/usr/bin/env python3
import shutil
from pathlib import Path
import sys

# Liste des déplacements ou copies à effectuer :
# ("source", "destination")
MOVES = [
    # Exemples – adapte ces lignes à ton arborescence réelle
    ("prompts/_archive", "scaffolds/openai"),
    ("kpis.py", "src/autobot/ecommerce/kpis.py"),
    ("src/data/providers.py", "src/data/providers.py"),
    # Ajoute ici toutes les paires (src, dst) dont tu as besoin
]

def main():
    for src, dst in MOVES:
        s = Path(src)
        d = Path(dst)
        if not s.exists():
            print(f"⚠️ Source introuvable : {s}", file=sys.stderr)
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            # copie récursive
            for item in s.rglob("*"):
                rel = item.relative_to(s)
                target = d / rel
                if item.is_dir():
                    target.mkdir(exist_ok=True)
                else:
                    shutil.copy2(item, target)
            print(f"✔ Copied directory {s} → {d}")
        else:
            shutil.copy2(s, d)
            print(f"✔ Copied file {s} → {d}")

if __name__ == "__main__":
    main()
