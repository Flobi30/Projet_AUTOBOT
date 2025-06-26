#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/ubuntu/repos/Projet_AUTOBOT/src')

from autobot.config import load_api_keys
from autobot.backtest.core import real_backtest_engine
from autobot.providers import alphavantage, twelvedata, fred

def test_extended_forex_trading():
    """Test extended forex trading capabilities"""
    print("=== Testing Extended Forex Trading ===")
    
    load_api_keys()
    
    forex_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF", "NZD/USD"]
    strategies = ["currency_correlation", "carry_trade", "economic_indicator"]
    
    for pair in forex_pairs:
        print(f"\nTesting {pair}...")
        for strategy in strategies:
            try:
                result = real_backtest_engine.run_strategy_backtest(
                    strategy_name=strategy,
                    symbol=pair,
                    periods=50,
                    initial_capital=1000.0,
                    params={'correlation_threshold': 0.7, 'interest_rate_diff': 0.02, 'momentum_period': 14}
                )
                
                if 'error' not in result:
                    print(f"✅ {pair} ({strategy}): Return {result['total_return']:.2f}%, Sharpe {result['sharpe_ratio']:.2f}")
                else:
                    print(f"❌ {pair} ({strategy}): {result['error']}")
                    
            except Exception as e:
                print(f"❌ {pair} ({strategy}): Exception {e}")

def test_commodities_trading():
    """Test commodities trading capabilities"""
    print("\n=== Testing Commodities Trading ===")
    
    commodities = ["XAU/USD", "XAG/USD", "WTI/USD", "NG/USD", "XPT/USD"]
    strategies = ["commodity_momentum", "moving_average_crossover"]
    
    for commodity in commodities:
        print(f"\nTesting {commodity}...")
        for strategy in strategies:
            try:
                result = real_backtest_engine.run_strategy_backtest(
                    strategy_name=strategy,
                    symbol=commodity,
                    periods=50,
                    initial_capital=1000.0,
                    params={'fast_period': 10, 'slow_period': 30, 'momentum_period': 21, 'volatility_period': 14}
                )
                
                if 'error' not in result:
                    print(f"✅ {commodity} ({strategy}): Return {result['total_return']:.2f}%, Sharpe {result['sharpe_ratio']:.2f}")
                else:
                    print(f"❌ {commodity} ({strategy}): {result['error']}")
                    
            except Exception as e:
                print(f"❌ {commodity} ({strategy}): Exception {e}")

def test_economic_indicators():
    """Test economic indicators integration"""
    print("\n=== Testing Economic Indicators ===")
    
    indicators = [
        ("US Interest Rates", fred.get_interest_rates("US")),
        ("EU Interest Rates", fred.get_interest_rates("EU")),
        ("US Inflation", fred.get_inflation_data("US")),
        ("US GDP", fred.get_gdp_data("US"))
    ]
    
    for name, data in indicators:
        if 'error' not in data:
            print(f"✅ {name}: Data available")
        else:
            print(f"❌ {name}: {data['error']}")

def test_api_connectivity():
    """Test API connectivity for all providers"""
    print("\n=== Testing API Connectivity ===")
    
    try:
        data = twelvedata.get_forex_data('EUR/USD', '1h')
        if 'error' not in data and 'values' in data:
            print("✅ TwelveData: Connected and working")
        else:
            print(f"❌ TwelveData: {data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"❌ TwelveData: Exception {e}")
    
    try:
        data = alphavantage.get_fx_daily('EUR', 'USD')
        if 'error' not in data:
            print("✅ AlphaVantage: Connected and working")
        else:
            print(f"❌ AlphaVantage: {data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"❌ AlphaVantage: Exception {e}")
    
    try:
        data = fred.get_economic_data('FEDFUNDS')
        if 'error' not in data:
            print("✅ FRED: Connected and working")
        else:
            print(f"❌ FRED: {data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"❌ FRED: Exception {e}")

if __name__ == "__main__":
    print("🚀 AUTOBOT Extended Forex & Commodities Trading Test")
    print("=" * 70)
    
    test_api_connectivity()
    test_extended_forex_trading()
    test_commodities_trading()
    test_economic_indicators()
    
    print("\n" + "=" * 70)
    print("🎯 Extended Trading Capabilities Test Complete")
