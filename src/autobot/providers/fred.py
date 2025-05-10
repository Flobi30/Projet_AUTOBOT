import os
if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.fred import *  # mode mock
else:
    import requests
    
    def get_time_series(*args, **kwargs):
        """Stub auto-généré pour tests."""
        r = requests.get(*args, **kwargs)
        r.raise_for_status()
        return r.json()
    
    get_series = get_time_series
    get_fred = get_time_series

get_time_series = get_series