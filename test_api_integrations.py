#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/home/ubuntu/Projet_AUTOBOT/src')

from dotenv import load_dotenv
load_dotenv()

def test_api_providers():
    print("Testing API provider integrations...")
    
    try:
        from autobot.providers import alphavantage
        print("✓ Alpha Vantage provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('ALPHA_VANTAGE_API_KEY') else 'No'}")
    except Exception as e:
        print(f"✗ Alpha Vantage provider error: {e}")
    
    try:
        from autobot.providers import newsapi
        print("✓ NewsAPI provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('NEWSAPI_KEY') else 'No'}")
    except Exception as e:
        print(f"✗ NewsAPI provider error: {e}")
    
    try:
        from autobot.providers import twelvedata
        print("✓ Twelve Data provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('TWELVE_DATA_API_KEY') else 'No'}")
    except Exception as e:
        print(f"✗ Twelve Data provider error: {e}")
    
    try:
        from autobot.providers import fred
        print("✓ FRED provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('FRED_API_KEY') else 'No'}")
    except Exception as e:
        print(f"✗ FRED provider error: {e}")
    
    try:
        from autobot.providers import shopify
        print("✓ Shopify provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('SHOPIFY_API_KEY') else 'No'}")
        print(f"  Shop Name configured: {'Yes' if os.getenv('SHOPIFY_SHOP_NAME') else 'No'}")
    except Exception as e:
        print(f"✗ Shopify provider error: {e}")
    
    try:
        from autobot.providers import binance
        print("✓ Binance provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('BINANCE_API_KEY') else 'No'}")
        print(f"  API Secret configured: {'Yes' if os.getenv('BINANCE_API_SECRET') else 'No'}")
    except Exception as e:
        print(f"✗ Binance provider error: {e}")
    
    try:
        from autobot.providers import coinbase
        print("✓ Coinbase provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('COINBASE_API_KEY') else 'No'}")
        print(f"  API Secret configured: {'Yes' if os.getenv('COINBASE_API_SECRET') else 'No'}")
    except Exception as e:
        print(f"✗ Coinbase provider error: {e}")
    
    try:
        from autobot.providers import kraken
        print("✓ Kraken provider imported successfully")
        print(f"  API Key configured: {'Yes' if os.getenv('KRAKEN_API_KEY') else 'No'}")
        print(f"  API Secret configured: {'Yes' if os.getenv('KRAKEN_API_SECRET') else 'No'}")
    except Exception as e:
        print(f"✗ Kraken provider error: {e}")

if __name__ == "__main__":
    test_api_providers()
