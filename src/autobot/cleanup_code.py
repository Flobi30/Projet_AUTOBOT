#!/usr/bin/env python3
# cleanup_code.py
import re
from pathlib import Path

# 1) les répertoires à nettoyer
roots = [Path("src"), Path("prompts")]

# 2) expression pour virer tout caractère non‑ASCII
non_ascii = re.compile(r"[^\x00-\x7F]")

# 3) expression pour supprimer la ligne de scaffold d’intro (commençant par Here’s ou Here''s ou “““Here)
scaffold_intro = re.compile(r"(?m)^(Here’s|Here''s|“““Here).*\r?\n")

for root in roots:
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        # supprime ligne intro scaffold
        text = scaffold_intro.sub("", text)
        # remplace fancy quotes par simple quote
        text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
        # supprime box‑drawing chars
        text = text.replace("│", "").replace("└", "")
        # supprime tout caractère non‑ASCII résiduel
        text = non_ascii.sub("", text)
        # assure LF uniquement et pas de BOM
        text = text.replace("\r\n", "\n")
        py.write_text(text, encoding="utf-8")
        print(f"Cleaned: {py}")

