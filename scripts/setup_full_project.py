#!/usr/bin/env python3
"""
scripts/setup_full_project.py

1. Crée l’arborescence providers prod & mocks
2. Génère les stubs prod et mocks manquants (non destructif)
3. Ajoute dans chaque provider les alias attendus par router.py
4. Met à jour validate_all.py pour injecter PYTHONPATH
5. Crée .env.example et .vscode/settings.json

Usage (à la racine du projet) :
    python scripts/setup_full_project.py
"""
import os, shutil, re, json
from pathlib import Path

# 1. Détection des chemins
ROOT          = Path(__file__).parent.parent.resolve()
SRC           = ROOT / "src"
AUTOBOT       = SRC / "autobot"
PROD_PROV     = AUTOBOT / "providers"
MOCK_PROV     = AUTOBOT / "data" / "providers"
SCRIPTS       = ROOT / "scripts"
VALIDATE_PY   = SCRIPTS / "validate_all.py"
ENV_EXAMPLE   = ROOT / ".env.example"
VSCODE_FOLDER = ROOT / ".vscode"

# 2. Crée les dossiers nécessaires
for d in (AUTOBOT, PROD_PROV, MOCK_PROV, VSCODE_FOLDER):
    d.mkdir(parents=True, exist_ok=True)

# 3. __init__.py pour chaque package
for pkg in (AUTOBOT, PROD_PROV, MOCK_PROV):
    (pkg / "__init__.py").touch(exist_ok=True)

# 4. Stubs « prod » (uniquement s’ils n’existent pas)
stubs = {
    "ccxt_provider.py": """
import ccxt
def fetch_ticker(symbol: str, exchange_id: str = "binance"):
    ex = getattr(ccxt, exchange_id)()
    return ex.fetch_ticker(symbol)
get_ccxt_provider = fetch_ticker
""",
    "coingecko.py": """
import requests
BASE="https://api.coingecko.com/api/v3"
def get_prices(ids:list[str], vs_currency:str="usd")->dict:
    r=requests.get(f"{BASE}/coins/markets", params={"ids":",".join(ids),"vs_currency":vs_currency})
    r.raise_for_status(); return r.json()
def get_defi()->dict:
    r=requests.get(f"{BASE}/global/decentralized_finance_defi"); r.raise_for_status(); return r.json()
get_coingecko = get_prices
""",
    "fred.py": """
import os,requests
KEY=os.getenv("FRED_KEY","")
def get_series(series_id:str)->dict:
    r=requests.get("https://api.stlouisfed.org/fred/series/observations", params={"series_id":series_id,"api_key":KEY})
    r.raise_for_status(); return r.json()
get_fred = get_series
""",
    "newsapi.py": """
import os,requests
KEY=os.getenv("NEWSAPI_KEY","")
def get_news(q:str)->dict:
    r=requests.get("https://newsapi.org/v2/everything", params={"q":q,"apiKey":KEY})
    r.raise_for_status(); return r.json()
get_newsapi = get_news
""",
    "shopify.py": """
import os,requests
KEY=os.getenv("SHOPIFY_KEY",""); SHOP=os.getenv("SHOPIFY_SHOP_NAME","")
def get_orders()->dict:
    r=requests.get(f"https://{SHOP}.myshopify.com/admin/api/2025-01/orders.json", headers={"X-Shopify-Access-Token":KEY})
    r.raise_for_status(); return r.json()
def get_customers()->dict:
    r=requests.get(f"https://{SHOP}.myshopify.com/admin/api/2025-01/customers.json", headers={"X-Shopify-Access-Token":KEY})
    r.raise_for_status(); return r.json()
get_shopify_orders = get_orders
get_shopify_customers = get_customers
""",
    "twelvedata.py": """
import os,requests
BASE="https://api.twelvedata.com"; KEY=os.getenv("TWELVE_KEY","")
def get_intraday(symbol:str,interval:str="1min")->dict:
    r=requests.get(f"{BASE}/time_series", params={"symbol":symbol,"interval":interval,"apikey":KEY})
    r.raise_for_status(); return r.json()
def get_eod(symbol:str)->dict:
    r=requests.get(f"{BASE}/eod", params={"symbol":symbol,"apikey":KEY})
    r.raise_for_status(); return r.json()
get_twelvedata = get_intraday
""",
    "alphavantage.py": """
import os,requests
BASE="https://www.alphavantage.co/query"; KEY=os.getenv("ALPHA_KEY","")
def get_intraday(symbol:str,interval:str="1min")->dict:
    r=requests.get(BASE, params={"function":"TIME_SERIES_INTRADAY","symbol":symbol,"interval":interval,"apikey":KEY})
    r.raise_for_status(); return r.json()
def get_time_series(symbol:str,series_type:str="DAILY")->dict:
    r=requests.get(BASE, params={"function":f"TIME_SERIES_{series_type}","symbol":symbol,"apikey":KEY})
    r.raise_for_status(); return r.json()
def get_technical_indicators(symbol:str,indicator:str,interval:str="daily")->dict:
    r=requests.get(BASE, params={"function":indicator,"symbol":symbol,"interval":interval,"apikey":KEY})
    r.raise_for_status(); return r.json()
get_alphavantage = get_intraday
"""
}

for fname, code in stubs.items():
    path = PROD_PROV / fname
    if not path.exists():
        path.write_text(code.lstrip(), encoding="utf-8")
        print(f"✔️ Stub prod créé : {fname}")

# 5. Mocks (non destructif)
for fname in stubs:
    path = MOCK_PROV / fname
    if not path.exists():
        # stub minimal
        func = re.search(r"def\s+([^(]+)\(", stubs[fname]).group(1)
        path.write_text(f"def {func}(*a,**k): return {{'mocked':'{fname}'}}", encoding="utf-8")
        print(f"✔️ Mock créé : {fname}")

# 6. Ajout des alias attendus par router.py
# D’après les erreurs, router importe :
mapping = {
    "ccxt_provider.py":       [("get_ccxt_provider","fetch_ticker")],
    "coingecko.py":           [("get_intraday","get_prices")],
    "fred.py":                [("get_time_series","get_series"),("get_fred","get_series")],
    "newsapi.py":             [("get_time_series","get_news"),("get_newsapi","get_news")],
    "shopify.py":             [("get_shopify","get_orders")],
    "twelvedata.py":          [("get_intraday","get_intraday"),("get_twelvedata","get_intraday")],
    "alphavantage.py":        [("get_alphavantage","get_intraday"),("get_alphavantage_ts","get_time_series"),("get_alphavantage_ti","get_technical_indicators")],
}

for fname, aliases in mapping.items():
    path = PROD_PROV / fname
    if not path.exists(): continue
    text = path.read_text(encoding="utf-8").splitlines()
    updated = False
    for alias, target in aliases:
        # si l'alias n'existe pas déjà
        if not any(l.strip().startswith(f"{alias} =") for l in text):
            # vérifier que target existe
            if any(l.strip().startswith(f"def {target}") for l in text):
                text.append(f"{alias} = {target}")
                updated = True
            else:
                print(f"⚠️ cible '{target}' introuvable dans {fname}")
    if updated:
        path.write_text("\n".join(text)+"\n", encoding="utf-8")
        print(f"✅ Aliases ajoutés dans {fname}")

# 7. Mise à jour de validate_all.py (injection PYTHONPATH)
if VALIDATE_PY.exists():
    txt = VALIDATE_PY.read_text(encoding="utf-8").splitlines()
    if not any("sys.path.insert" in l for l in txt):
        idx = next((i for i,l in enumerate(txt) if l.startswith(("import","from"))),0)
        inj = ["import sys, os",
               "sys.path.insert(0, os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, 'src')))",
               ""]
        txt = txt[:idx] + inj + txt[idx:]
        VALIDATE_PY.write_text("\n".join(txt)+"\n", encoding="utf-8")
        print("✔️ validate_all.py mis à jour")

# 8. .env.example non-destructif
env = """\
# Exemple de variables d'environnement
PYTHONPATH=src
ALPHA_KEY=
TWELVE_KEY=
FRED_KEY=
NEWSAPI_KEY=
SHOPIFY_KEY=
SHOPIFY_SHOP_NAME=
"""
if not ENV_EXAMPLE.exists():
    ENV_EXAMPLE.write_text(env, encoding="utf-8")
    print("✔️ .env.example créé")

# 9. VSCode settings.json
vscode_conf = {
    "python.envFile": "${workspaceFolder}/.env",
    "terminal.integrated.env.windows": {
        "PYTHONPATH": "${workspaceFolder}/src"
    }
}
with open(VSCODE_FOLDER/"settings.json","w",encoding="utf-8") as f:
    json.dump(vscode_conf,f,indent=2)
    print("✔️ .vscode/settings.json créé ou mis à jour")

print("\n✅ Tout est prêt ! Lance maintenant en PowerShell :")
print("   python .\\scripts\\validate_all.py; pytest")

