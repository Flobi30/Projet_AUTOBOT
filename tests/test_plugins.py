# tests/test_plugins.py

import os
import glob
import importlib.util
import pytest

# Fixture qui mocke requests.get pour tous les plugins
@pytest.fixture(autouse=True)
def patch_requests(monkeypatch):
    import requests
    class DummyResp:
        def __init__(self): pass
        def raise_for_status(self): pass
        def json(self): return {"dummy": "value"}
    def fake_get(url, headers=None):
        return DummyResp()
    monkeypatch.setattr(requests, "get", fake_get)
    return None

def test_all_plugins_have_get_data():
    """
    Pour chaque fichier src/autobot/plugins/*.py,
    on importe dynamiquement et on vérifie get_data().
    """
    plugin_files = glob.glob("src/autobot/plugins/*.py")
    assert plugin_files, "Aucun plugin trouvé dans src/autobot/plugins/"
    for path in plugin_files:
        # module name = path sans .py, convert slash en dot
        mod_name = path[:-3].replace("/", ".").replace("\\", ".")
        spec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # chaque stub doit définir get_data()
        assert hasattr(mod, "get_data"), f"{mod_name} n’a pas get_data()"
        # appeler la fonction ne doit pas planter
        data = mod.get_data()
        assert isinstance(data, dict), f"{mod_name}.get_data() doit retourner un dict"
