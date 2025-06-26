#!/usr/bin/env python3
# cleanup_scaffolds.py

import re
from pathlib import Path

def find_scaffold_paths() -> list[Path]:
    """
    Retourne la liste des fichiers *_scaffold.py sous src/.
    """
    root = Path(__file__).parent / "src"
    return list(root.rglob("*_scaffold.py"))

def clean_file(path: Path) -> None:
    """
    Ouvre le fichier, nettoie les caractères indésirables
    et supprime la ligne d'intro générée par GPT, puis
    réécrit le contenu en UTF-8 (LF).
    """
    text = path.read_text(encoding="utf-8")

    # 1) Remplace les quotes typographiques par des quotes simples/doubles
    text = re.sub(r"[‘’‚‛]", "'", text)
    text = re.sub(r"[“”„]", '"', text)

    # 2) Supprime les box‐drawing chars (ex: ─│└┴┬…)
    text = re.sub(r"[│┤└┴┬├─┼┐┌┘]", "", text)

    # 3) Supprime la ligne d’intro type "Here's a scaffold…" ou "Here’s a scaffold…"
    text = re.sub(r"^.*Here('?|’)s.*\n", "", text, flags=re.IGNORECASE | re.MULTILINE)

    # 4) Force LF uniquement
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5) Écrit en UTF-8 LF
    path.write_text(text, encoding="utf-8")
    print(f"✔ cleaned {path.relative_to(Path.cwd())}")

def main():
    print("🚀 cleanup_scaffolds.py démarre…\n")
    paths = find_scaffold_paths()
    if not paths:
        print("⚠️ Aucun fichier *_scaffold.py trouvé sous src/.")
        return

    for p in paths:
        clean_file(p)

if __name__ == "__main__":
    main()

