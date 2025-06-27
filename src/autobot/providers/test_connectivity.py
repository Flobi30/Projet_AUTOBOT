import asyncio
import os
from typing import Dict, Any

try:
    from autobot.config import load_api_keys
    keys_loaded = load_api_keys()
    print(f"Loaded {keys_loaded} API keys for connectivity testing")
except Exception as e:
    print(f"Warning: Could not load API keys: {e}")

from . import binance, alphavantage, twelvedata, fred, newsapi, shopify, coinbase, kraken

async def test_all_providers() -> Dict[str, Any]:
    """Test connectivity for all API providers"""
    results = {}
    
    # Test Binance
    try:
        ticker = binance.get_ticker("BTCUSDT")
        if 'error' in ticker:
            results['binance'] = {'status': 'error', 'error': ticker['error']}
        else:
            results['binance'] = {'status': 'success', 'data': ticker}
    except Exception as e:
        results['binance'] = {'status': 'error', 'error': str(e)}
    
    # Test AlphaVantage
    try:
        data = alphavantage.get_intraday("AAPL")
        if 'error' in data:
            results['alphavantage'] = {'status': 'error', 'error': data['error']}
        else:
            results['alphavantage'] = {'status': 'success', 'data': data}
    except Exception as e:
        results['alphavantage'] = {'status': 'error', 'error': str(e)}
    
    # Test TwelveData
    try:
        data = twelvedata.get_intraday("AAPL")
        if 'error' in data:
            results['twelvedata'] = {'status': 'error', 'error': data['error']}
        else:
            results['twelvedata'] = {'status': 'success', 'data': data}
    except Exception as e:
        results['twelvedata'] = {'status': 'error', 'error': str(e)}
    
    # Test FRED
    try:
        data = fred.get_economic_data("GDP")
        if 'error' in data:
            results['fred'] = {'status': 'error', 'error': data['error']}
        else:
            results['fred'] = {'status': 'success', 'data': data}
    except Exception as e:
        results['fred'] = {'status': 'error', 'error': str(e)}
    
    # Test NewsAPI
    try:
        data = newsapi.get_news("bitcoin")
        if 'error' in data:
            results['newsapi'] = {'status': 'error', 'error': data['error']}
        else:
            results['newsapi'] = {'status': 'success', 'data': data}
    except Exception as e:
        results['newsapi'] = {'status': 'error', 'error': str(e)}
    
    # Test Coinbase
    try:
        data = coinbase.get_ticker("BTC-USD")
        if 'error' in data:
            results['coinbase'] = {'status': 'error', 'error': data['error']}
        else:
            results['coinbase'] = {'status': 'success', 'data': data}
    except Exception as e:
        results['coinbase'] = {'status': 'error', 'error': str(e)}
    
    # Test Kraken
    try:
        data = kraken.get_ticker("XBTUSD")
        if 'error' in data:
            results['kraken'] = {'status': 'error', 'error': data['error']}
        else:
            results['kraken'] = {'status': 'success', 'data': data}
    except Exception as e:
        results['kraken'] = {'status': 'error', 'error': str(e)}
    
    return results

def print_connectivity_report():
    """Print a formatted connectivity report"""
    results = asyncio.run(test_all_providers())
    
    print("=== API Connectivity Report ===")
    working_providers = 0
    total_providers = len(results)
    
    for provider, result in results.items():
        status = "✅" if result['status'] == 'success' else "❌"
        print(f"{status} {provider.upper()}: {result['status']}")
        if result['status'] == 'error':
            print(f"   Error: {result['error']}")
        else:
            working_providers += 1
    
    print(f"\nSummary: {working_providers}/{total_providers} providers working")
    return results

if __name__ == "__main__":
    print_connectivity_report()
