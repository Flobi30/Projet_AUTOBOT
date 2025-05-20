"""
Module de compatibilité pour autobot_guardian.
Ce module réexporte les fonctions d'autobot_guardian pour maintenir
la compatibilité avec le code existant.
"""

from autobot.autobot_guardian import AutobotGuardian

def get_logs() -> dict:
    """
    Compatibilité avec l'ancien code.
    
    Returns:
        dict: Logs du système
    """
    return AutobotGuardian.get_logs()

def get_metrics() -> dict:
    """
    Compatibilité avec l'ancien code.
    
    Returns:
        dict: Métriques du système
    """
    return {
        "cpu_usage": 0.0,
        "memory_usage": 0.0,
        "endpoint_latency_ms": 0.0
    }
