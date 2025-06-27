#!/usr/bin/env python3
"""
Test Kraken API connectivity to understand empty response issue
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

def test_kraken_api():
    print("=== Testing Kraken API Connectivity ===")
    
    try:
        from autobot.config import load_api_keys
        keys_loaded = load_api_keys()
        print(f"Loaded {keys_loaded} API keys")
        
        from autobot.providers.kraken import get_ticker
        import json
        
        print("\n=== Testing Kraken XBTUSD ===")
        result = get_ticker('XBTUSD')
        print(json.dumps(result, indent=2))
        
        print("\n=== Testing Kraken BTCUSD ===")
        result2 = get_ticker('BTCUSD')
        print(json.dumps(result2, indent=2))
        
        print("\n=== Testing Kraken XXBTZUSD ===")
        result3 = get_ticker('XXBTZUSD')
        print(json.dumps(result3, indent=2))
        
    except Exception as e:
        print(f"Error testing Kraken API: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_kraken_api()
