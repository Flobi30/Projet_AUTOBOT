"""
Module pour la surveillance des logs de sécurité.
"""
import os
import json
import time
import threading
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timedelta
from .ip_blocker import IPBlocker

class LogMonitor:
    def __init__(self, log_file: str = "/var/log/autobot/security.log", check_interval: int = 60):
        self.log_file = log_file
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.ip_blocker = IPBlocker()
        
        self.attack_threshold = int(os.getenv("AUTOBOT_ATTACK_THRESHOLD", "3"))
        self.suspicious_ips: Dict[str, int] = {}  # IP -> nombre d'événements suspects
        
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w") as f:
                pass
    
    def start(self) -> None:
        """Démarre la surveillance des logs dans un thread séparé."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._monitor_loop)
            self.thread.daemon = True
            self.thread.start()
            print(f"✅ [SECURITY] Surveillance des logs démarrée")
    
    def stop(self) -> None:
        """Arrête la surveillance des logs."""
        self.running = False
        if self.thread:
            self.thread.join()
            print(f"✅ [SECURITY] Surveillance des logs arrêtée")
    
    def _monitor_loop(self) -> None:
        """Boucle principale de surveillance des logs."""
        last_position = 0
        
        while self.running:
            try:
                with open(self.log_file, "r") as f:
                    f.seek(last_position)
                    new_lines = f.readlines()
                    last_position = f.tell()
                
                for line in new_lines:
                    self._process_log_line(line)
                
                self._check_thresholds()
                
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"❌ [SECURITY] Erreur lors de la surveillance des logs: {str(e)}")
                time.sleep(self.check_interval)
    
    def _process_log_line(self, line: str) -> None:
        """Traite une ligne de log de sécurité."""
        try:
            event = json.loads(line)
            ip = event.get("ip")
            event_type = event.get("type")
            
            if ip and event_type in ["attack", "bruteforce", "blocked"]:
                if ip not in self.suspicious_ips:
                    self.suspicious_ips[ip] = 0
                self.suspicious_ips[ip] += 1
        except:
            pass
    
    def _check_thresholds(self) -> None:
        """Vérifie si des IPs dépassent les seuils de détection."""
        for ip, count in list(self.suspicious_ips.items()):
            if count >= self.attack_threshold:
                self.ip_blocker.block_ip(ip)
                self.suspicious_ips[ip] = 0
