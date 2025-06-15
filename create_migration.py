#!/usr/bin/env python3
"""
Manual migration script to add new database models
This script creates the new tables while preserving existing data
"""
import sqlite3
import os
from datetime import datetime

def create_migration():
    db_path = 'data/autobot.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if new tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='params_to_test'")
        if cursor.fetchone():
            print("Migration already applied - params_to_test table exists")
            return True
        
        print("Creating params_to_test table...")
        cursor.execute('''
            CREATE TABLE params_to_test (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                timeframe TEXT DEFAULT '1h',
                initial_capital REAL DEFAULT 500.0,
                parameters TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                backtest_result_id TEXT,
                FOREIGN KEY(backtest_result_id) REFERENCES backtest_results(id)
            )
        ''')
        
        print("Creating capital_history table...")
        cursor.execute('''
            CREATE TABLE capital_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                capital_value REAL NOT NULL,
                equity_change REAL DEFAULT 0.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(backtest_id) REFERENCES backtest_results(id)
            )
        ''')
        
        # Add new columns to existing backtest_results table
        print("Adding new columns to backtest_results table...")
        try:
            cursor.execute('ALTER TABLE backtest_results ADD COLUMN initial_capital REAL DEFAULT 500.0')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
            print("initial_capital column already exists")
        
        try:
            cursor.execute('ALTER TABLE backtest_results ADD COLUMN final_equity REAL')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
            print("final_equity column already exists")
        
        try:
            cursor.execute('ALTER TABLE backtest_results ADD COLUMN total_return REAL')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
            print("total_return column already exists")
        
        try:
            cursor.execute('ALTER TABLE backtest_results ADD COLUMN max_drawdown REAL')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
            print("max_drawdown column already exists")
        
        try:
            cursor.execute('ALTER TABLE backtest_results ADD COLUMN sharpe_ratio REAL')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
            print("sharpe_ratio column already exists")
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Current tables: {tables}")
        
        return True
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = create_migration()
    if success:
        print("Database migration completed successfully")
    else:
        print("Database migration failed")
        exit(1)
