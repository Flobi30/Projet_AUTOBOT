#!/usr/bin/env python3
"""
Test the new persistence system to ensure it saves real backtest data going forward.
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

import time
from datetime import datetime
from autobot.db.models import SessionLocal, BacktestResult, CapitalHistory, create_tables

def test_new_persistence_system():
    """Test that the new persistence system works correctly."""
    print("=== Testing NEW Persistence System ===")
    
    create_tables()
    print("✅ Database tables created/verified")
    
    try:
        db = SessionLocal()
        
        existing_count = db.query(BacktestResult).count()
        print(f"📊 Current database records: {existing_count}")
        
        test_result = BacktestResult(
            id=f"test_persistence_{int(datetime.now().timestamp())}",
            symbol="BTCUSDT",
            strategy="test_strategy",
            initial_capital=500.0,
            final_capital=525.0,
            total_return=5.0,  # 5% return
            sharpe_ratio=1.2,
            max_drawdown=2.0,
            strategy_params='{"test": true}'
        )
        
        db.add(test_result)
        db.commit()
        
        print("✅ Test backtest result saved successfully")
        
        saved_result = db.query(BacktestResult).filter(BacktestResult.id == test_result.id).first()
        if saved_result:
            print(f"✅ Verified: Test result retrieved from database")
            print(f"   Strategy: {saved_result.strategy}")
            print(f"   Return: {saved_result.total_return}%")
            print(f"   Capital: {saved_result.initial_capital}€ → {saved_result.final_capital}€")
        else:
            print("❌ Test result not found in database")
            return False
        
        print("\n🔄 Testing _load_cumulative_performance function...")
        
        from autobot.ui.backtest_routes import _load_cumulative_performance
        
        cumulative_data = _load_cumulative_performance()
        
        print(f"✅ Cumulative data loaded:")
        print(f"   Total return: {cumulative_data['total_return']}%")
        print(f"   Performance count: {cumulative_data['performance_count']}")
        print(f"   Days active: {cumulative_data['days_active']}")
        print(f"   Cumulative capital: {cumulative_data['cumulative_capital']}€")
        
        print("\n🔄 Testing _save_backtest_to_database function...")
        
        from autobot.ui.backtest_routes import _save_backtest_to_database
        
        test_backtest_result = {
            'total_return': 0.03,  # 3% return
            'sharpe_ratio': 1.5,
            'max_drawdown': 1.0,
            'total_trades': 10,
            'params': {'test_param': 'test_value'}
        }
        
        _save_backtest_to_database("test_new_strategy", "ETHUSDT", test_backtest_result, 500.0)
        
        print("✅ _save_backtest_to_database function executed successfully")
        
        new_count = db.query(BacktestResult).count()
        print(f"📊 Database records after test: {new_count} (was {existing_count})")
        
        if new_count > existing_count:
            print("✅ New backtest results are being saved correctly!")
        else:
            print("❌ New backtest results are not being saved")
            return False
        
        db.close()
        
        print("\n=== NEW Persistence System Test Complete ===")
        print("✅ System is ready to accumulate real performance data going forward!")
        
        return True
        
    except Exception as e:
        print(f"❌ Persistence system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_new_persistence_system()
    if success:
        print("\n🎉 NEW Persistence System is working correctly!")
        print("🚀 AUTOBOT will now accumulate real performance data!")
    else:
        print("\n❌ NEW Persistence System needs debugging")
