#!/usr/bin/env python3
"""
Check database contents to verify if it contains real or synthetic data.
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from autobot.db.models import SessionLocal, BacktestResult, CapitalHistory
from datetime import datetime

def check_database_contents():
    """Check what's actually in the database."""
    print("=== Checking Database Contents ===")
    
    try:
        db = SessionLocal()
        
        backtest_count = db.query(BacktestResult).count()
        print(f"📊 BacktestResult records: {backtest_count}")
        
        if backtest_count > 0:
            first_records = db.query(BacktestResult).limit(5).all()
            print(f"\n📋 First {len(first_records)} BacktestResult records:")
            for record in first_records:
                print(f"   ID: {record.id}")
                print(f"   Strategy: {record.strategy}")
                print(f"   Symbol: {record.symbol}")
                print(f"   Return: {record.total_return}%")
                print(f"   Capital: {record.initial_capital}€ → {record.final_capital}€")
                print(f"   Timestamp: {record.timestamp}")
                print(f"   ---")
            
            latest_records = db.query(BacktestResult).order_by(BacktestResult.timestamp.desc()).limit(3).all()
            print(f"\n📋 Latest {len(latest_records)} BacktestResult records:")
            for record in latest_records:
                print(f"   ID: {record.id}")
                print(f"   Strategy: {record.strategy}")
                print(f"   Return: {record.total_return}%")
                print(f"   Timestamp: {record.timestamp}")
                print(f"   ---")
        
        capital_count = db.query(CapitalHistory).count()
        print(f"\n📊 CapitalHistory records: {capital_count}")
        
        if capital_count > 0:
            latest_capital = db.query(CapitalHistory).order_by(CapitalHistory.timestamp.desc()).limit(3).all()
            print(f"\n📋 Latest {len(latest_capital)} CapitalHistory records:")
            for record in latest_capital:
                print(f"   Capital: {record.capital_value}€")
                print(f"   Strategy: {record.strategy_name}")
                print(f"   Timestamp: {record.timestamp}")
                print(f"   ---")
        
        if backtest_count > 0:
            total_return = db.query(BacktestResult.total_return).all()
            returns = [r[0] for r in total_return if r[0] is not None]
            
            if returns:
                avg_return = sum(returns) / len(returns)
                total_cumulative = sum(returns)
                print(f"\n📈 Performance Summary:")
                print(f"   Total backtests: {len(returns)}")
                print(f"   Average return: {avg_return:.2f}%")
                print(f"   Cumulative return: {total_cumulative:.2f}%")
                
                unique_returns = len(set(returns))
                if unique_returns < len(returns) * 0.1:  # Less than 10% unique values
                    print(f"⚠️  WARNING: Only {unique_returns} unique returns out of {len(returns)} - possible synthetic data")
                else:
                    print(f"✅ Data appears natural: {unique_returns} unique returns")
        
        db.close()
        
        if backtest_count == 0:
            print(f"\n🎯 CONCLUSION: Database is EMPTY - ready for new real data")
            return "empty"
        elif backtest_count > 1000:
            print(f"\n🎯 CONCLUSION: Database contains {backtest_count} records - likely SYNTHETIC")
            return "synthetic"
        else:
            print(f"\n🎯 CONCLUSION: Database contains {backtest_count} records - likely REAL test data")
            return "real"
        
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        import traceback
        traceback.print_exc()
        return "error"

if __name__ == "__main__":
    result = check_database_contents()
    print(f"\n🔍 Database status: {result}")
