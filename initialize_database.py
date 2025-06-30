#!/usr/bin/env python3
"""
Initialize the database tables for AUTOBOT persistence system.
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from autobot.db.models import create_tables

def initialize_database():
    """Initialize database tables for AUTOBOT."""
    print("=== Initializing AUTOBOT Database ===")
    
    try:
        create_tables()
        print("✅ Database tables created successfully")
        
        db_path = '/home/ubuntu/repos/Projet_AUTOBOT/data/autobot.db'
        if os.path.exists(db_path):
            print(f"✅ Database file created at: {db_path}")
            file_size = os.path.getsize(db_path)
            print(f"📊 Database file size: {file_size} bytes")
        else:
            print(f"❌ Database file not found at: {db_path}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = initialize_database()
    if success:
        print("\n🎉 Database initialized successfully!")
    else:
        print("\n❌ Database initialization failed")
