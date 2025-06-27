"""
Adaptive Capital Management System for AUTOBOT

This module provides adaptive capital management that learns and optimizes
strategies based on available capital amounts.
"""

from .capital_manager import AdaptiveCapitalManager

adaptive_capital_manager = AdaptiveCapitalManager(initial_capital=500.0)

__all__ = ['AdaptiveCapitalManager', 'adaptive_capital_manager']
