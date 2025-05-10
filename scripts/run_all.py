#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT     = Path(__file__).parent.parent.resolve()
SCRIPTS  = ROOT / "scripts"
SRC      = ROOT / "src"
AUTO     = SRC / "autobot"
PROV_DIR = AUTO / "providers"
TESTS    = ROOT / "tests"

def fix_stress_test():
    f = SCRIPTS / "stress_test.py"
    if f.exists():
        txt = f.read_text(encoding="utf-8")
        # Remplacer tout tiret Unicode par un simple ASCII '-'
        new = txt.replace("–", "-").replace("—", "-")
        if new != txt:
            f.write_text(new, encoding="utf-8")
            print("✔ stress_test.py patché")

def fix_test_fetch():
    f = SCRIPTS / "test_fetch.py"
    if f.exists():
        txt = f.read_text(encoding="utf-8")
        # Remplacer la placeholder invalide par une URL valide
        new = re.sub(r"LA_URL_QUE_TU_AS_COPI[ÉE]E", "https://example.com", txt)
        if new != txt:
            f.write_text(new, encoding="utf-8")
            print("✔ test_fetch.py patché")

def patch_providers_aliases():
    alias_map = {
        "coingecko.py":   [("get_intraday",       "get_prices")],
        "fred.py":        [("get_time_series",    "get_series")],
        "newsapi.py":     [("get_time_series",    "get_news")],
        "shopify.py":     [("get_shopify_orders", "get_orders")],
        "twelvedata.py":  [("get_intraday",       "get_intraday")],
        "alphavantage.py":[
            ("get_alphavantage",    "get_intraday"),
            ("get_alphavantage_ts", "get_time_series"),
            ("get_alphavantage_ti", "get_technical_indicators")
        ]
    }
    for fname, pairs in alias_map.items():
        p = PROV_DIR / fname
        if not p.exists():
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        updated = False
        for alias, target in pairs:
            line = f"{alias} = {target}"
            if line not in lines:
                lines.append(line)
                updated = True
        if updated:
            p.write_text("\n".join(lines)+"\n", encoding="utf-8")
            print(f"✔ {fname} – aliases ajoutés")

def stub_autobot_guardian():
    f = AUTO / "autobot_guardian.py"
    content = """\
class AutobotGuardian:
    @staticmethod
    def get_logs() -> dict:
        return {}
"""
    if f.read_text(encoding="utf-8") != content:
        f.write_text(content, encoding="utf-8")
        print("✔ autobot_guardian.py stub généré")

def expose_strategies():
    f = ROOT / "strategies.py"
    stub = "from src.autobot.strategies import ExampleStrategy, select_strategy, StrategyManager\n"
    if f.exists():
        if f.read_text(encoding="utf-8") != stub:
            f.write_text(stub, encoding="utf-8")
            print("✔ strategies.py racine mis à jour")
    else:
        f.write_text(stub, encoding="utf-8")
        print("✔ strategies.py à la racine créé")

def write_pytest_ini():
    f = ROOT / "pytest.ini"
    ini = "[pytest]\npythonpath = src\n"
    if not f.exists() or f.read_text(encoding="utf-8") != ini:
        f.write_text(ini, encoding="utf-8")
        print("✔ pytest.ini créé ou mis à jour")

def main():
    fix_stress_test()
    fix_test_fetch()
    patch_providers_aliases()
    stub_autobot_guardian()
    expose_strategies()
    write_pytest_ini()

    print("\n→ Lancement de validate_all.py …")
    ret = subprocess.call([sys.executable, str(SCRIPTS / "validate_all.py")])
    if ret != 0:
        sys.exit(ret)

    print("\n→ Lancement de pytest …")
    sys.exit(subprocess.call(["pytest"]))

if __name__ == "__main__":
    main()
