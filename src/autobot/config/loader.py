import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

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
        
        key_mapping = {
            'BINANCE_API_KEY': 'BINANCE_API_KEY',
            'BINANCE_SECRET_KEY': 'BINANCE_API_SECRET',
            'ALPHA_VANTAGE_API_KEY': 'ALPHA_VANTAGE_API_KEY',
            'TWELVE_DATA_API_KEY': 'TWELVE_DATA_API_KEY',
            'FRED_API_KEY': 'FRED_API_KEY',
            'NEWS_API_KEY': 'NEWSAPI_KEY',
            'COINBASE_API_KEY': 'COINBASE_API_KEY',
            'COINBASE_SECRET_KEY': 'COINBASE_API_SECRET',
            'KRAKEN_API_KEY': 'KRAKEN_API_KEY',
            'KRAKEN_SECRET_KEY': 'KRAKEN_API_SECRET',
            'SHOPIFY_API_KEY': 'SHOPIFY_API_KEY',
            'SHOPIFY_SECRET_KEY': 'SHOPIFY_SECRET_KEY',
            'STRIPE_API_KEY': 'STRIPE_API_KEY',
            'STRIPE_PUBLISHABLE_KEY': 'STRIPE_PUBLISHABLE_KEY',
            'STRIPE_WEBHOOK_SECRET': 'STRIPE_WEBHOOK_SECRET'
        }
        
        for config_key, env_key in key_mapping.items():
            if config_key in api_keys and api_keys[config_key]:
                os.environ[env_key] = api_keys[config_key]
                loaded_count += 1
                print(f"Loaded {config_key} -> {env_key}")
                logger.info(f"Set environment variable {env_key} from config key {config_key}")
                
        print(f"Loaded {loaded_count} API keys into environment variables")
        return loaded_count
                
    except Exception as e:
        print(f"Error loading API keys: {e}")
        return 0
