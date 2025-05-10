# src/data/providers.py

class AlphaVantageProvider:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def _fetch(self, *args, **kwargs):
        # placeholder de la vraie requête
        raise NotImplementedError

    def get_time_series(self, symbol):
        try:
            return self._fetch(symbol)
        except Exception:
            return {}

class TwelveDataProvider:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def _fetch(self, *args, **kwargs):
        raise NotImplementedError

    def get_time_series(self, symbol):
        try:
            return self._fetch(symbol)
        except Exception:
            return {}

class CCXTProvider:
    def __init__(self, exchange=None):
        self.exchange = exchange

    def get_time_series(self, symbol):
        # placeholder
        return {}
