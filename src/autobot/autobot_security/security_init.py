"""
Script d'initialisation des composants de sécurité.
"""
import os
import threading
from .log_monitor import LogMonitor
from .ip_blocker import IPBlocker

def initialize_security():
    """Initialise tous les composants de sécurité."""
    print("🔒 [SECURITY] Initialisation des composants de sécurité...")
    
    ip_blocker = IPBlocker()
    
    log_monitor = LogMonitor()
    log_monitor.start()
    
    malicious_ip = os.getenv("AUTOBOT_BLOCK_IP", "187.234.19.188")
    if malicious_ip:
        ip_blocker.block_ip(malicious_ip)
    
    print("✅ [SECURITY] Composants de sécurité initialisés avec succès")
