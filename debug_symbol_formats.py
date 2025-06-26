#!/usr/bin/env python3

import sys
sys.path.append('src')
from autobot.config import load_api_keys
from autobot.providers import alphavantage, twelvedata

def debug_symbol_formats():
    """Debug different symbol formats for forex and commodities"""
    print("=== DEBUGGING SYMBOL FORMATS ===")
    
    load_api_keys()
    
    forex_symbols = [
        ("USD/JPY", "USD", "JPY"),
        ("USDJPY", "USD", "JPY"),
        ("AUD/USD", "AUD", "USD"),
        ("AUDUSD", "AUD", "USD"),
        ("USD/CAD", "USD", "CAD"),
        ("USDCAD", "USD", "CAD")
    ]
    
    print("\n1. Testing Forex Symbol Formats:")
    for symbol, from_sym, to_sym in forex_symbols:
        print(f"\nTesting {symbol}:")
        
        try:
            data = twelvedata.get_forex_data(symbol, '1h')
            if 'error' not in data and 'values' in data and data['values']:
                print(f"  ✅ TwelveData {symbol}: {len(data['values'])} data points")
            else:
                print(f"  ❌ TwelveData {symbol}: {data.get('error', 'No data')}")
        except Exception as e:
            print(f"  ❌ TwelveData {symbol}: Exception {e}")
        
        try:
            data = alphavantage.get_fx_daily(from_sym, to_sym)
            if 'error' not in data:
                keys = list(data.keys())
                print(f"  ✅ AlphaVantage {from_sym}/{to_sym}: Keys {keys}")
            else:
                print(f"  ❌ AlphaVantage {from_sym}/{to_sym}: {data.get('error', 'No data')}")
        except Exception as e:
            print(f"  ❌ AlphaVantage {from_sym}/{to_sym}: Exception {e}")
    
    commodity_symbols = [
        "XAU/USD", "XAUUSD", "GOLD", "GC=F",
        "XAG/USD", "XAGUSD", "SILVER", "SI=F",
        "WTI/USD", "WTIUSD", "CL=F", "CRUDE_OIL_WTI",
        "NG/USD", "NGAS", "NG=F", "NATURAL_GAS"
    ]
    
    print("\n2. Testing Commodity Symbol Formats:")
    for symbol in commodity_symbols:
        print(f"\nTesting {symbol}:")
        
        try:
            data = twelvedata.get_commodity_data(symbol, '1day')
            if 'error' not in data and 'values' in data and data['values']:
                print(f"  ✅ TwelveData {symbol}: {len(data['values'])} data points")
            else:
                print(f"  ❌ TwelveData {symbol}: {data.get('error', 'No data')}")
        except Exception as e:
            print(f"  ❌ TwelveData {symbol}: Exception {e}")
        
        try:
            data = alphavantage.get_commodity_data(symbol)
            if 'error' not in data:
                keys = list(data.keys())
                print(f"  ✅ AlphaVantage {symbol}: Keys {keys}")
            else:
                print(f"  ❌ AlphaVantage {symbol}: {data.get('error', 'No data')}")
        except Exception as e:
            print(f"  ❌ AlphaVantage {symbol}: Exception {e}")

if __name__ == "__main__":
    debug_symbol_formats()
