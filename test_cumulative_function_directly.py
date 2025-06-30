#!/usr/bin/env python3
"""
Test the _load_cumulative_performance function directly to debug the issue.
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

def test_cumulative_function():
    """Test the cumulative performance function directly."""
    print("=== Testing _load_cumulative_performance Function Directly ===")
    
    try:
        from autobot.ui.backtest_routes import _load_cumulative_performance
        
        print("🔄 Calling _load_cumulative_performance()...")
        result = _load_cumulative_performance()
        
        print(f"✅ Function returned:")
        print(f"   Total Return: {result['total_return']}%")
        print(f"   Performance Count: {result['performance_count']}")
        print(f"   Cumulative Capital: {result['cumulative_capital']}€")
        print(f"   Days Active: {result['days_active']}")
        print(f"   Total Trades: {result['total_trades']}")
        print(f"   Avg Sharpe: {result['avg_sharpe']}")
        
        if result['performance_count'] > 0:
            print(f"✅ Function is loading REAL database data")
        else:
            print(f"❌ Function is returning empty/default data")
        
        return result
        
    except Exception as e:
        print(f"❌ Error testing cumulative function: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = test_cumulative_function()
    if result:
        print(f"\n🎯 CONCLUSION: Function {'works' if result['performance_count'] > 0 else 'needs fixing'}")
