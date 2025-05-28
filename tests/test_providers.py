# tests/test_providers.py
import pytest
from data.providers import AlphaVantageProvider, TwelveDataProvider, CCXTProvider

@pytest.mark.parametrize("ProviderClass", [AlphaVantageProvider, TwelveDataProvider])
def test_time_series_empty_on_error(monkeypatch, ProviderClass):
    # Simule une exception interne
    monkeypatch.setattr(ProviderClass, "_fetch", lambda self, *a, **k: (_ for _ in ()).throw(Exception("fail")))
    prov = ProviderClass()
    assert prov.get_time_series("SYM") == {}

def test_ccxt_provider_returns_dict():
    cp = CCXTProvider()
    assert isinstance(cp.get_time_series("SYM"), dict)
