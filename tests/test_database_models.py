import pytest
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
import sys

# Add project root to path
sys.path.append('/root/Projet_AUTOBOT')
from db.models import Base, BacktestResult, ParamsToTest, CapitalHistory

class TestDatabaseModels:
    
    @pytest.fixture
    def in_memory_db(self):
        """Create an in-memory SQLite database for testing"""
        engine = create_engine('sqlite:///:memory:', echo=False)
        Base.metadata.create_all(engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        yield session
        
        session.close()
    
    def test_backtest_result_creation(self, in_memory_db):
        """Test creating a BacktestResult model"""
        backtest = BacktestResult(
            id="test_backtest_1",
            symbol="BTC/USDT",
            strategy="RSI",
            result_data='{"test": "data"}',
            initial_capital=1000.0,
            final_equity=1200.0,
            total_return=0.2,
            max_drawdown=-0.05,
            sharpe_ratio=1.5
        )
        
        in_memory_db.add(backtest)
        in_memory_db.commit()
        
        # Retrieve and verify
        retrieved = in_memory_db.query(BacktestResult).filter_by(id="test_backtest_1").first()
        assert retrieved is not None
        assert retrieved.symbol == "BTC/USDT"
        assert retrieved.strategy == "RSI"
        assert retrieved.initial_capital == 1000.0
        assert retrieved.final_equity == 1200.0
        assert retrieved.total_return == 0.2
        assert retrieved.max_drawdown == -0.05
        assert retrieved.sharpe_ratio == 1.5
    
    def test_params_to_test_creation(self, in_memory_db):
        """Test creating a ParamsToTest model"""
        params = ParamsToTest(
            id="test_params_1",
            symbol="ETH/USDT",
            strategy="Moving Average",
            timeframe="4h",
            initial_capital=500.0,
            parameters={"period": 20, "threshold": 0.02},
            status="completed"
        )
        
        in_memory_db.add(params)
        in_memory_db.commit()
        
        # Retrieve and verify
        retrieved = in_memory_db.query(ParamsToTest).filter_by(id="test_params_1").first()
        assert retrieved is not None
        assert retrieved.symbol == "ETH/USDT"
        assert retrieved.strategy == "Moving Average"
        assert retrieved.timeframe == "4h"
        assert retrieved.initial_capital == 500.0
        assert retrieved.parameters["period"] == 20
        assert retrieved.parameters["threshold"] == 0.02
        assert retrieved.status == "completed"
    
    def test_capital_history_creation(self, in_memory_db):
        """Test creating a CapitalHistory model"""
        # First create a backtest result
        backtest = BacktestResult(
            id="test_backtest_2",
            symbol="BTC/USDT",
            strategy="RSI",
            initial_capital=1000.0
        )
        in_memory_db.add(backtest)
        in_memory_db.commit()
        
        # Create capital history entry
        capital_entry = CapitalHistory(
            backtest_id="test_backtest_2",
            timestamp=datetime.utcnow(),
            capital_value=1050.0,
            equity_change=50.0
        )
        
        in_memory_db.add(capital_entry)
        in_memory_db.commit()
        
        # Retrieve and verify
        retrieved = in_memory_db.query(CapitalHistory).filter_by(backtest_id="test_backtest_2").first()
        assert retrieved is not None
        assert retrieved.capital_value == 1050.0
        assert retrieved.equity_change == 50.0
        assert retrieved.backtest_id == "test_backtest_2"
    
    def test_model_relationships(self, in_memory_db):
        """Test relationships between models"""
        # Create backtest result
        backtest = BacktestResult(
            id="test_backtest_3",
            symbol="BTC/USDT",
            strategy="RSI",
            initial_capital=1000.0
        )
        in_memory_db.add(backtest)
        
        # Create related params
        params = ParamsToTest(
            id="test_params_2",
            symbol="BTC/USDT",
            strategy="RSI",
            backtest_result_id="test_backtest_3"
        )
        in_memory_db.add(params)
        
        # Create capital history
        capital_entry = CapitalHistory(
            backtest_id="test_backtest_3",
            timestamp=datetime.utcnow(),
            capital_value=1100.0,
            equity_change=100.0
        )
        in_memory_db.add(capital_entry)
        
        in_memory_db.commit()
        
        # Test relationships
        retrieved_backtest = in_memory_db.query(BacktestResult).filter_by(id="test_backtest_3").first()
        assert len(retrieved_backtest.params_tests) == 1
        assert len(retrieved_backtest.capital_history) == 1
        assert retrieved_backtest.params_tests[0].id == "test_params_2"
        assert retrieved_backtest.capital_history[0].capital_value == 1100.0
    
    def test_existing_table_compatibility(self, in_memory_db):
        """Test compatibility with existing backtest_results table structure"""
        # Create a backtest result using only the original fields
        backtest = BacktestResult(
            id="compatibility_test",
            symbol="BTC/USDT",
            strategy="RSI",
            result_data='{"original": "format"}'
        )
        
        in_memory_db.add(backtest)
        in_memory_db.commit()
        
        # Verify it works with original schema
        retrieved = in_memory_db.query(BacktestResult).filter_by(id="compatibility_test").first()
        assert retrieved is not None
        assert retrieved.symbol == "BTC/USDT"
        assert retrieved.strategy == "RSI"
        assert retrieved.result_data == '{"original": "format"}'
        # New fields should have default values
        assert retrieved.initial_capital == 500.0

def run_smoke_test():
    """Standalone smoke test for quick verification"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    print("Running database models smoke test...")
    
    # Create in-memory database
    engine = create_engine('sqlite:///:memory:', echo=True)
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    # Create test data
    backtest = BacktestResult(
        id="smoke_test_1",
        symbol="BTC/USDT",
        strategy="RSI",
        result_data='{"test": "smoke test"}',
        initial_capital=500.0
    )
    
    session.add(backtest)
    session.commit()
    
    # Verify
    retrieved = session.query(BacktestResult).first()
    print(f"Smoke test successful: Created backtest with ID {retrieved.id}")
    
    session.close()
    return True

if __name__ == "__main__":
    run_smoke_test()
