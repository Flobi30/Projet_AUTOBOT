"""
Module de compatibilité pour les tests.
Permet d'importer les stratégies depuis le package strategies.
"""
from src.strategies import ExampleStrategy, StrategyManager, select_strategy

import sys
sys.modules['strategies'] = sys.modules['src.strategies']
