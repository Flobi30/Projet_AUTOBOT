"""
Module de stratégies pour AUTOBOT.
Contient les différentes stratégies de trading.
"""

class ExampleStrategy:
    """
    Stratégie d'exemple pour les tests.
    """
    def __init__(self, name):
        self.name = name
        self.description = f"Example strategy named {name}"

class StrategyManager:
    """
    Gestionnaire de stratégies.
    """
    def __init__(self, strategies=None):
        self.strategies = strategies or {}
    
    def get(self, name):
        """
        Récupère une stratégie par son nom.
        
        Args:
            name: Nom de la stratégie
            
        Returns:
            La stratégie correspondante
        """
        return self.strategies.get(name)

def select_strategy(name, manager):
    """
    Sélectionne une stratégie par son nom.
    
    Args:
        name: Nom de la stratégie
        manager: Gestionnaire de stratégies
        
    Returns:
        La stratégie correspondante
        
    Raises:
        ValueError: Si la stratégie n'existe pas
    """
    if not name:
        raise ValueError("Strategy name cannot be empty")
    
    strategy = manager.get(name)
    if not strategy:
        raise ValueError(f"Unknown strategy: {name}")
    
    return strategy
