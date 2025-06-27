from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

Base = declarative_base()

class CapitalHistory(Base):
    __tablename__ = 'capital_history'
    
    id = Column(Integer, primary_key=True)
    backtest_id = Column(String, ForeignKey('backtest_results.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    capital_value = Column(Float)
    strategy_name = Column(String)
    performance_metrics = Column(Text)
    
    backtest = relationship("BacktestResult", back_populates="capital_history")

class BacktestResult(Base):
    __tablename__ = 'backtest_results'
    
    id = Column(String, primary_key=True)
    symbol = Column(String)
    strategy = Column(String)
    initial_capital = Column(Float)
    final_capital = Column(Float)
    total_return = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    strategy_params = Column(Text)
    
    capital_history = relationship("CapitalHistory", back_populates="backtest")

DATABASE_URL = "sqlite:///data/autobot.db"
os.makedirs("data", exist_ok=True)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
