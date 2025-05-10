#!/usr/bin/env python3
"""
scripts/setup_test_env.py

1) Crée les stubs data/providers si manquants
2) Prépare chaque provider prod pour basculer en mode mock si USE_MOCK=1
3) Stub autobot_guardian.get_logs()
4) Expose strategies.py à la racine
5) Modifie validate_all.py pour injecter USE_MOCK et PYTHONPATH
Usage:
    python scripts/setup_test_env.py
    python scripts/validate_all.py   # ou pytest
"""

import os, json
from pathlib import Path

ROOT      = Path(__file__).parent.parent.resolve()
SRC       = ROOT / "src"
AUTO      = SRC / "autobot"
PROV_DIR  = AUTO / "providers"
MOCK_DIR  = AUTO / "data" / "providers"
SCRIPTS   = ROOT / "scripts"
VALIDATE  = SCRIPTS / "validate_all.py"

# 1) Assurer que data/providers contient un stub par provider
PROV_DIR.mkdir(parents=True, exist_ok=True)
MOCK_DIR.mkdir(parents=True, exist_ok=True)
for stub in PROV_DIR.iterdir():
    if not stub.name.endswith(".py") or stub.name == "__init__.py":
        continue
    mock = MOCK_DIR / stub.name
    if not mock.exists():
        # stub minimal : renvoie dict{"mocked": filename}
        fn = next((n for n in stub.read_text().split() if n.startswith("def ")), "def get_data").split()[1].split("(")[0]
        mock.write_text(f"def {fn}(*a,**k):\n    return {{'mocked':'{stub.stem}'}}\n",
                        encoding="utf-8")

# 2) Mettre à jour chaque provider pour déléguer aux mocks si USE_MOCK=1
for prod in PROV_DIR.glob("*.py"):
    text = prod.read_text(encoding="utf-8").splitlines()
    # si on a déjà la ligne de flag, on skip
    if any("if os.getenv(\"USE_MOCK\")" in l for l in text):
        continue

    # on fabrique un wrapper
    header = [
        "import os",
        "if os.getenv(\"USE_MOCK\") == \"1\":",
        f"    from autobot.data.providers.{prod.stem} import *  # mode mock",
        "else:",
    ]
    # indenter l'ancien contenu
    body = ["    " + l for l in text]
    prod.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    print(f"🔀 Patch mock-switch dans {prod.name}")

# 3) Stub pour autobot_guardian.get_logs()
guardian = AUTO / "autobot_guardian.py"
guardian.write_text("""\
def get_logs() -> dict:
    \"\"\"Stub pour l’endpoint /logs en test\"\"\"
    return {}
""", encoding="utf-8")
print("✔️ Stub guardian mis en place")

# 4) Exposer strategies à la racine
(ROOT / "strategies.py").write_text("from src.autobot.strategies import *\n", encoding="utf-8")
print("✔️ strategies.py à la racine créé")

# 5) Mettre à jour validate_all.py pour injecter USE_MOCK et PYTHONPATH
if VALIDATE.exists():
    lines = VALIDATE.read_text(encoding="utf-8").splitlines()
    # injecter USE_MOCK=1 avant tout import
    if not any("os.environ[\"USE_MOCK\"]" in l for l in lines):
        inj = [
            "import os",
            "os.environ[\"USE_MOCK\"] = \"1\"",
            "import sys",
            "sys.path.insert(0, os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, 'src')))",
            ""
        ]
        # trouver le premier import/from
        idx = next((i for i,l in enumerate(lines) if l.startswith(("import","from"))), 0)
        lines = lines[:idx] + inj + lines[idx:]
        VALIDATE.write_text("\n".join(lines)+"\n", encoding="utf-8")
        print("✔️ validate_all.py mis à jour pour USE_MOCK & PYTHONPATH")

print("\n✅ Environnement de test prêt !")
print("→ Pour tester, lance : python scripts/validate_all.py  (ou pytest)")
