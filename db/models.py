from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

Base = declarative_base()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/autobot.db')
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class BacktestResult(Base):
    __tablename__ = 'backtest_results'
    
    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False)
    strategy = Column(String, nullable=False)
    result_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Enhanced fields for better analytics
    initial_capital = Column(Float, default=500.0)
    final_equity = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    
    # Relationships
    params_tests = relationship("ParamsToTest", back_populates="backtest_result")
    capital_history = relationship("CapitalHistory", back_populates="backtest_result")

class ParamsToTest(Base):
    __tablename__ = 'params_to_test'
    
    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False)
    strategy = Column(String, nullable=False)
    timeframe = Column(String, default="1h")
    initial_capital = Column(Float, default=500.0)
    parameters = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")  # pending, running, completed, failed
    
    # Foreign key to link with backtest results
    backtest_result_id = Column(String, ForeignKey('backtest_results.id'), nullable=True)
    
    # Relationship
    backtest_result = relationship("BacktestResult", back_populates="params_tests")

class CapitalHistory(Base):
    __tablename__ = 'capital_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    backtest_id = Column(String, ForeignKey('backtest_results.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    capital_value = Column(Float, nullable=False)
    equity_change = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    backtest_result = relationship("BacktestResult", back_populates="capital_history")

def get_db():
    """Database session dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all tables in the database"""
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully")
