import os
if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.ccxt_provider import *  # mode mock
else:
    import requests
    
    def get_ccxt_provider(*args, **kwargs):
        """Stub auto-généré pour tests."""
        r = requests.get(*args, **kwargs)
        r.raise_for_status()
        return r.json()
    
    fetch_ticker = get_ccxt_provider
