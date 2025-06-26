#!/usr/bin/env python3

import sys
import os
import asyncio
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

async def test_updated_data_provider():
    """Test the updated real market data provider with TwelveData as primary"""
    print("=== Testing Updated Data Provider with TwelveData Primary ===")
    
    try:
        print("1. Testing RealMarketDataProvider...")
        from autobot.data.real_market_data import RealMarketDataProvider
        
        provider = RealMarketDataProvider()
        
        print("   Testing crypto data (BTC/USD)...")
        crypto_data = provider.get_crypto_data("BTCUSDT", limit=10)
        if not crypto_data.empty:
            current_price = float(crypto_data['close'].iloc[-1])
            print(f"   ✅ BTC price: ${current_price:,.2f}")
        else:
            print("   ❌ No crypto data received")
        
        print("   Testing forex data (EUR/USD)...")
        forex_data = provider.get_forex_data("EUR/USD")
        if not forex_data.empty:
            current_rate = float(forex_data['close'].iloc[-1])
            print(f"   ✅ EUR/USD rate: {current_rate:.4f}")
        else:
            print("   ❌ No forex data received")
        
        print("   Testing commodity data (Gold)...")
        commodity_data = provider.get_commodity_data("XAU/USD")
        if not commodity_data.empty:
            gold_price = float(commodity_data['close'].iloc[-1])
            print(f"   ✅ Gold price: ${gold_price:,.2f}")
        else:
            print("   ❌ No commodity data received")
        
        print("\n2. Testing RealBacktestEngine with updated provider...")
        from autobot.data.real_market_data import RealBacktestEngine
        
        engine = RealBacktestEngine()
        
        result = engine.run_strategy_backtest(
            strategy_name="moving_average_crossover",
            symbol="BTCUSDT",
            periods=20,
            initial_capital=1000.0
        )
        
        print(f"   Backtest result: {result}")
        if result.get('total_return', 0) != 0:
            print(f"   ✅ Real backtest working - Return: {result.get('total_return', 0):.4f}")
        else:
            print("   ❌ Backtest still returning zero")
        
        print("\n3. Testing API endpoint with updated data...")
        from autobot.ui.backtest_routes import get_backtest_status
        
        api_result = await get_backtest_status()
        print(f"   API Status: {api_result.get('status')}")
        print(f"   Data Source: {api_result.get('data_source')}")
        print(f"   Total Return: {api_result.get('total_return')}")
        
        if api_result.get('total_return', 0) != 0:
            print("   ✅ API endpoint returning real data!")
        else:
            print("   ❌ API endpoint still returning zero")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing updated provider: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_updated_data_provider())
    sys.exit(0 if success else 1)
