
"""This module handles profit calculations and capital management for AUTOBOT."""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CapitalManager:
    """Enhanced capital management system for AUTOBOT."""
    
    def __init__(self, data_file: str = "config/capital_data.json"):
        self.data_file = data_file
        self.ensure_data_file_exists()
    
    def ensure_data_file_exists(self):
        """Ensure the capital data file exists."""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        if not os.path.exists(self.data_file):
            initial_data = {
                "users": {},
                "global_settings": {
                    "default_initial_capital": 0,
                    "currency": "EUR"
                }
            }
            with open(self.data_file, 'w') as f:
                json.dump(initial_data, f, indent=2)
    
    def get_user_capital_data(self, user_id: str) -> Dict[str, Any]:
        """Get capital data for a specific user."""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
            
            user_data = data.get("users", {}).get(user_id, {})
            
            return {
                "initial_capital": user_data.get("initial_capital", 0),
                "current_capital": user_data.get("current_capital", 0),
                "profit": user_data.get("profit", 0),
                "roi": user_data.get("roi", 0),
                "trading_allocation": user_data.get("trading_allocation", 0),
                "ecommerce_allocation": user_data.get("ecommerce_allocation", 0),
                "capital_history": user_data.get("capital_history", []),
                "transactions": user_data.get("transactions", []),
                "total_capital": user_data.get("current_capital", 0),
                "available_for_withdrawal": user_data.get("available_for_withdrawal", 0),
                "in_use": user_data.get("in_use", 0)
            }
        except Exception as e:
            logger.error(f"Error reading capital data: {str(e)}")
            return self._get_default_capital_data()
    
    def _get_default_capital_data(self) -> Dict[str, Any]:
        """Get default capital data structure."""
        return {
            "initial_capital": 0,
            "current_capital": 0,
            "profit": 0,
            "roi": 0,
            "trading_allocation": 0,
            "ecommerce_allocation": 0,
            "capital_history": [],
            "transactions": [],
            "total_capital": 0,
            "available_for_withdrawal": 0,
            "in_use": 0
        }
    
    def update_user_capital(self, user_id: str, capital_data: Dict[str, Any]) -> bool:
        """Update capital data for a specific user."""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
            
            if "users" not in data:
                data["users"] = {}
            
            if user_id not in data["users"]:
                data["users"][user_id] = self._get_default_capital_data()
            
            data["users"][user_id].update(capital_data)
            data["users"][user_id]["last_updated"] = datetime.now().isoformat()
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        except Exception as e:
            logger.error(f"Error updating capital data: {str(e)}")
            return False
    
    def add_transaction(self, user_id: str, transaction: Dict[str, Any]) -> bool:
        """Add a transaction to user's history."""
        try:
            capital_data = self.get_user_capital_data(user_id)
            transactions = capital_data.get("transactions", [])
            
            transaction["timestamp"] = datetime.now().isoformat()
            transactions.append(transaction)
            
            return self.update_user_capital(user_id, {"transactions": transactions})
        except Exception as e:
            logger.error(f"Error adding transaction: {str(e)}")
            return False

capital_manager = CapitalManager()

def get_user_capital_data(user_id: str) -> Dict[str, Any]:
    """Get capital data for a user."""
    return capital_manager.get_user_capital_data(user_id)

def update_user_capital(user_id: str, capital_data: Dict[str, Any]) -> bool:
    """Update capital data for a user."""
    return capital_manager.update_user_capital(user_id, capital_data)

