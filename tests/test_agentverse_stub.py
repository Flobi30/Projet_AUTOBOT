# tests/test_agentverse_stub.py
import os
import pytest
from autobot.plugins.agentverse import get_data

class DummyResp:
    def __init__(self, json_data):
        self._json = json_data
    def raise_for_status(self):
        pass
    def json(self):
        return self._json

@pytest.fixture(autouse=True)
def patch_requests(monkeypatch):
    import requests
    def fake_get(url, headers=None):
        # vérifie qu’on appelle bien le bon stub
        assert "agentverse" in url
        return DummyResp({"hello": "world"})
    monkeypatch.setattr(requests, "get", fake_get)
    return None

def test_get_data_returns_dummy():
    data = get_data()
    assert data == {"hello": "world"}
