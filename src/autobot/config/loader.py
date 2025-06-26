import json
import os
from pathlib import Path

def load_api_keys():
    """Load API keys from config/api_keys.json into environment variables"""
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "api_keys.json"
    
    if not config_path.exists():
        print(f"Warning: API keys file not found at {config_path}")
        return 0
    
    try:
        with open(config_path, 'r') as f:
            api_keys = json.load(f)
        
        # Map JSON structure to environment variables
        loaded_count = 0
        
        # Binance
        if 'binance' in api_keys:
            if api_keys['binance'].get('api_key'):
                os.environ['BINANCE_API_KEY'] = api_keys['binance']['api_key']
                loaded_count += 1
            if api_keys['binance'].get('secret_key'):
                os.environ['BINANCE_API_SECRET'] = api_keys['binance']['secret_key']
                loaded_count += 1
        
        # Coinbase
        if 'coinbase' in api_keys:
            if api_keys['coinbase'].get('api_key'):
                os.environ['COINBASE_API_KEY'] = api_keys['coinbase']['api_key']
                loaded_count += 1
            if api_keys['coinbase'].get('secret_key'):
                os.environ['COINBASE_API_SECRET'] = api_keys['coinbase']['secret_key']
                loaded_count += 1
        
        # Kraken
        if 'kraken' in api_keys:
            if api_keys['kraken'].get('api_key'):
                os.environ['KRAKEN_API_KEY'] = api_keys['kraken']['api_key']
                loaded_count += 1
            if api_keys['kraken'].get('secret_key'):
                os.environ['KRAKEN_API_SECRET'] = api_keys['kraken']['secret_key']
                loaded_count += 1
        
        # Data providers
        if 'alpha_vantage' in api_keys:
            os.environ['ALPHA_VANTAGE_API_KEY'] = api_keys['alpha_vantage']
            loaded_count += 1
        
        if 'twelve_data' in api_keys:
            os.environ['TWELVE_DATA_API_KEY'] = api_keys['twelve_data']
            loaded_count += 1
        
        if 'fred' in api_keys:
            os.environ['FRED_API_KEY'] = api_keys['fred']
            loaded_count += 1
        
        if 'news_api' in api_keys:
            os.environ['NEWSAPI_KEY'] = api_keys['news_api']
            loaded_count += 1
        
        # Shopify
        if 'shopify' in api_keys:
            if api_keys['shopify'].get('api_key'):
                os.environ['SHOPIFY_API_KEY'] = api_keys['shopify']['api_key']
                loaded_count += 1
            if api_keys['shopify'].get('shop_name'):
                os.environ['SHOPIFY_SHOP_NAME'] = api_keys['shopify']['shop_name']
                loaded_count += 1
                
        print(f"Loaded {loaded_count} API keys into environment variables")
        return loaded_count
                
    except Exception as e:
        print(f"Error loading API keys: {e}")
        return 0
