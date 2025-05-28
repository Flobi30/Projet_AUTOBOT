#!/usr/bin/env python3
"""
scripts/validate_all.py

Valide en mocking:
1. Tous les providers (src/autobot/data/providers)
2. Tous les plugins IA (src/autobot/plugins)
3. Endpoints métiers via TestClient FastAPI
"""
import os
os.environ["USE_MOCK"] = "1"
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, 'src')))

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, 'src')))

import pytest
import importlib
import pathlib
from fastapi.testclient import TestClient
from autobot.main import app

client = TestClient(app)

# découvrir les modules
BASE = pathlib.Path(__file__).parent.parent / "src" / "autobot"
PROV_DIR = BASE / "providers"
PLUG_DIR = BASE / "plugins"

providers = [f.stem for f in PROV_DIR.glob("*.py")]
plugins   = [f.stem for f in PLUG_DIR.glob("*.py")]

@pytest.mark.parametrize("prov", providers)
def test_provider_mock(prov, monkeypatch):
    mod = importlib.import_module(f"autobot.providers.{prov}")
    # trouver la première fonction get_ ou fetch_
    fn_name = next(n for n in dir(mod) if n.startswith("get_") or n.startswith("fetch_"))
    fn = getattr(mod, fn_name)
    class Dummy:
        def raise_for_status(self): pass
        def json(self): return {"mocked": prov}
    monkeypatch.setenv("DUMMY","1")
    monkeypatch.setattr("requests.get", lambda *a,**k: Dummy())
    res = fn("TEST")
    assert res == {"mocked": prov}

@pytest.mark.parametrize("plug", plugins)
def test_plugin_mock(plug, monkeypatch):
    mod = importlib.import_module(f"autobot.plugins.{plug}")
    class Dummy:
        def raise_for_status(self): pass
        def json(self): return {"agent": plug}
    monkeypatch.setenv(f"{plug.upper()}_KEY", "dummy")
    monkeypatch.setattr("requests.get", lambda *a,**k: Dummy())
    res = mod.get_data()
    assert res == {"agent": plug}

def test_api_endpoints():
    # health
    r = client.get("/health")
    assert r.status_code == 200 and r.json().get("status") == "ok"
    # others
    for ep in ["/predict", "/backtest?symbol=IBM", "/metrics", "/logs", "/monitoring"]:
        if ep.startswith("/backtest") or ep.startswith("/predict") or ep.startswith("/metrics") or ep.startswith("/logs") or ep.startswith("/monitoring"):
            r = client.get(ep)
        else:
            r = client.post("/train")
        assert r.status_code in (200,201)

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
