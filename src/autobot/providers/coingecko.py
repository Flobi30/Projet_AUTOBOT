import os
if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.coingecko import *  # mode mock
else:
    import requests
    
    def get_intraday(*args, **kwargs):
        """Stub auto-généré pour tests."""
        r = requests.get(*args, **kwargs)
        r.raise_for_status()
        return r.json()
    
    get_prices = get_intraday
    get_coingecko = get_intraday

get_intraday = get_prices