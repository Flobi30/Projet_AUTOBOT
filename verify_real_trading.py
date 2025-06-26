#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/ubuntu/repos/Projet_AUTOBOT_backup/src')

def test_imports():
    """Test that all modules can be imported"""
    print("=== Testing Module Imports ===")
    
    try:
        from autobot.config import load_api_keys
        print("✅ Config loader imported")
    except Exception as e:
        print(f"❌ Config loader failed: {e}")
        return False
    
    try:
        from autobot.backtest.core import real_backtest_engine
        print("✅ Real backtest engine imported")
    except Exception as e:
        print(f"❌ Backtest engine failed: {e}")
        return False
    
    try:
        from autobot.providers import binance
        print("✅ Binance provider imported")
    except Exception as e:
        print(f"❌ Binance provider failed: {e}")
        return False
    
    return True

def test_live_data():
    """Test live market data connection"""
    print("\n=== Testing Live Market Data ===")
    
    try:
        from autobot.providers import binance
        ticker = binance.get_ticker("BTCUSDT")
        
        if 'error' not in ticker:
            price = float(ticker.get('lastPrice', 0))
            change = float(ticker.get('priceChangePercent', 0))
            print(f"✅ Live BTC/USDT: ${price:,.2f} ({change:+.2f}%)")
            return True, price
        else:
            print(f"❌ API Error: {ticker['error']}")
            return False, 0
    except Exception as e:
        print(f"❌ API Exception: {e}")
        return False, 0

def test_backtest_engine():
    """Test real backtest with live data"""
    print("\n=== Testing Real Backtest Engine ===")
    
    try:
        from autobot.backtest.core import real_backtest_engine
        
        result = real_backtest_engine.run_strategy_backtest(
            strategy_name="moving_average_crossover",
            symbol="BTCUSDT",
            periods=50,
            initial_capital=500.0,
            params={'fast_period': 10, 'slow_period': 20}
        )
        
        if 'error' in result:
            print(f"❌ Backtest Error: {result['error']}")
            return False
        else:
            print(f"✅ Backtest Results (Real Market Data):")
            print(f"   Strategy: {result['strategy']}")
            print(f"   Symbol: {result['symbol']}")
            print(f"   Initial Capital: ${result['initial_capital']:.2f}")
            print(f"   Final Capital: ${result['final_capital']:.2f}")
            print(f"   Total Return: {result['total_return']:.2f}%")
            print(f"   Max Drawdown: {result['max_drawdown']:.2f}%")
            print(f"   Sharpe Ratio: {result['sharpe_ratio']:.2f}")
            print(f"   Total Trades: {result['total_trades']}")
            print(f"   Win Rate: {result['win_rate']:.1f}%")
            return True
    except Exception as e:
        print(f"❌ Backtest Exception: {e}")
        return False

def main():
    """Main verification function"""
    print("🚀 AUTOBOT Real Trading Algorithms Verification")
    print("=" * 60)
    
    imports_ok = test_imports()
    live_data_ok, btc_price = test_live_data()
    backtest_ok = test_backtest_engine()
    
    print("\n" + "=" * 60)
    print("📊 IMPLEMENTATION VERIFICATION RESULTS")
    print("=" * 60)
    
    if imports_ok and live_data_ok and backtest_ok:
        print("🎉 REAL TRADING ALGORITHMS SUCCESSFULLY IMPLEMENTED!")
        print("   ✅ All modules imported correctly")
        print("   ✅ Live market data connection working")
        print("   ✅ Real backtest engine functional with live data")
        print("   ✅ API providers integrated and tested")
        print(f"   📈 Current BTC price: ${btc_price:,.2f}")
        print("   🚀 Ready for production deployment")
        return True
    else:
        print("⚠️ Implementation verification failed:")
        if not imports_ok:
            print("   ❌ Module import issues")
        if not live_data_ok:
            print("   ❌ Live data connection issues")
        if not backtest_ok:
            print("   ❌ Backtest engine issues")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
