import os
if os.getenv("USE_MOCK") == "1":
    from autobot.data.providers.alphavantage import *  # mode mock
else:
    import requests
    
    def get_intraday(*args, **kwargs):
        """Stub auto-généré pour tests."""
        r = requests.get(*args, **kwargs)
        r.raise_for_status()
        return r.json()
    
    get_time_series = get_intraday
    get_technical_indicators = get_intraday
    get_alphavantage = get_intraday
    get_alphavantage_ts = get_intraday
    get_alphavantage_ti = get_intraday

get_technical_indicators = get_technical_indicators
get_alphavantage = get_intraday
get_alphavantage_ts = get_time_series
get_alphavantage_ti = get_technical_indicators
