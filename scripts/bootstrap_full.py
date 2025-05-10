#!/usr/bin/env python3
"""
Full Bootstrap Script for Autobot
- Generates data providers
- Generates IA agent plugin stubs from agents_shortlist.json
- Scaffolds FastAPI endpoints (business, providers, plugins, monitoring, logs)
- Implements RL training stub
- Updates Kubernetes manifests (HPA, liveness/readiness probes)
- Sets up production optimizations
"""
import os, json, re
from pathlib import Path

# Paths
ROOT = Path(__file__).parent.parent
SRC = ROOT / "src" / "autobot"
PLUGINS = SRC / "plugins"
PROVIDERS = SRC / "providers"
ROUTER = SRC / "router.py"
BACKTEST = SRC / "backtest_engine.py"
RL_TRAIN = SRC / "rl" / "train.py"
GUARDIAN = SRC / "autobot_guardian.py"
K8S = ROOT / "k8s"

# Ensure directories
PLUGINS.mkdir(parents=True, exist_ok=True)
PROVIDERS.mkdir(parents=True, exist_ok=True)

# 1) Data Providers
providers_code = {
    "alphavantage.py": """
import os, requests
API_KEY = os.getenv("ALPHAVANTAGE_KEY")
def get_intraday(symbol: str, interval="1min"):
    resp = requests.get("https://www.alphavantage.co/query", params={
        "function": "TIME_SERIES_INTRADAY", "symbol": symbol,
        "interval": interval, "apikey": API_KEY})
    resp.raise_for_status(); return resp.json()
""",
    "ccxt_provider.py": """
import os, ccxt
def fetch_ticker(symbol: str, exchange_id="binance"):
    ex = getattr(ccxt, exchange_id)()
    return ex.fetch_ticker(symbol)
""",
    "newsapi.py": """
import os, requests
KEY = os.getenv("NEWSAPI_KEY")
def get_news(q: str):
    resp = requests.get("https://newsapi.org/v2/everything", params={"q": q, "apiKey": KEY})
    resp.raise_for_status(); return resp.json()
""",
    "shopify.py": """
import os, requests
KEY = os.getenv("SHOPIFY_KEY")
def get_orders():
    resp = requests.get("https://your-shop.myshopify.com/admin/api/2025-01/orders.json",
                        headers={"X-Shopify-Access-Token": KEY})
    resp.raise_for_status(); return resp.json()
""",
    "fred.py": """
import os, requests
KEY = os.getenv("FRED_KEY")
def get_series(series_id: str):
    resp = requests.get("https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": series_id, "api_key": KEY})
    resp.raise_for_status(); return resp.json()
"""
}
for fname, code in providers_code.items():
    (PROVIDERS / fname).write_text(code.strip(), encoding="utf-8")

# 2) IA Agent plugin stubs
agents = json.load(open(ROOT / "agents_shortlist.json"))
for ag in agents:
    mod = re.sub(r"[^\w]+", "_", ag["name"].strip().lower())
    fpath = PLUGINS / f"{mod}.py"
    if not fpath.exists():
        fpath.write_text(f"""
import os, requests
def get_data():
    \"\"\"Stub for agent '{ag['name']}'\"\"\"
    headers = {{}}
    key = os.getenv("{mod.upper()}_KEY")
    if key: headers["Authorization"] = f"Bearer {{key}}"
    resp = requests.get("https://api.example.com/{mod}", headers=headers)
    resp.raise_for_status(); return resp.json()
""".strip(), encoding="utf-8")

# 3) Scaffold FastAPI router
router_txt = Path(ROUTER).read_text()
lines = router_txt.splitlines()

# Trouver où injecter : préférer "router = APIRouter()", sinon "app = FastAPI()"
insert_idx = None
for i, L in enumerate(lines):
    if re.match(r"\s*router\s*=\s*APIRouter\(\)", L):
        insert_idx = i + 1
        break
if insert_idx is None:
    for i, L in enumerate(lines):
        if re.match(r"\s*app\s*=\s*FastAPI\(\)", L):
            insert_idx = i + 1
            break
if insert_idx is None:
    raise RuntimeError("Impossible de trouver ni 'router = APIRouter()' ni 'app = FastAPI()' dans router.py")

# Préparer la liste des lignes à injecter
inserts = []
# -- provider endpoints
for fname in providers_code:
    name = fname[:-3]
    inserts.append(f"from autobot.providers.{name} import get_{name}")
    inserts.append(f"@router.get('/provider/{name}/{{param}}')\ndef prov_{name}(param: str): return get_{name}(param)")
# -- plugin endpoints
for ag in agents:
    mod = re.sub(r"[^\w]+", "_", ag["name"].strip().lower())
    inserts.append(f"from autobot.plugins.{mod} import get_data as get_{mod}")
    inserts.append(f"@router.get('/plugins/{mod}')\ndef plug_{mod}(): return get_{mod}()")
# -- business & monitoring endpoints
inserts.append("""
@router.get('/backtest')
def backtest(symbol: str):
    from autobot.backtest_engine import run_backtest
    return run_backtest(symbol)

@router.get('/predict')
def predict():
    return {'prediction': None}

@router.post('/train')
def train():
    from autobot.rl.train import start_training
    return {'job_id': start_training()}

@router.get('/metrics')
def metrics():
    from autobot.ecommerce.kpis import get_kpis
    return get_kpis()

@router.get('/logs')
def logs():
    from autobot.autobot_guardian import get_logs
    return get_logs()

@router.get('/monitoring')
def monitoring():
    from autobot.autobot_guardian import get_health
    return get_health()
""".strip())

# Insérer les lignes
new_lines = lines[:insert_idx] + inserts + lines[insert_idx:]
Path(ROUTER).write_text("\n".join(new_lines), encoding="utf-8")


# 4) RL stub
(BACKTEST).write_text("""
def run_backtest(symbol: str):
    return {'symbol': symbol, 'result': 'stub'}
""".strip(), encoding="utf-8")
(RL_TRAIN).write_text("""
import uuid
def start_training():
    return str(uuid.uuid4())
""".strip(), encoding="utf-8")

# 5) Update kubernetes probes and HPA
dep = K8S / "deployment.yaml"
d_txt = dep.read_text()
if "livenessProbe" not in d_txt:
    # insert probes under container spec
    d_txt = d_txt.replace("containers:", "containers:\n        livenessProbe:\n          httpGet:\n            path: /health\n            port: 8000\n          initialDelaySeconds: 10\n          periodSeconds: 10\n        readinessProbe:\n          httpGet:\n            path: /health\n            port: 8000\n          initialDelaySeconds: 5\n          periodSeconds: 5\n")
    dep.write_text(d_txt, encoding="utf-8")
hpa = K8S / "hpa.yaml"
hpa_txt = hpa.read_text()
if "metrics:" not in hpa_txt:
    hpa.write_text(hpa_txt + """
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
""", encoding="utf-8")

print("Bootstrap complete: providers, plugins, endpoints, RL, k8s.")
