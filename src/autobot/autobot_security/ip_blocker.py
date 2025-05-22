"""
Module pour bloquer les IPs suspectes avec iptables.
"""
import os
import subprocess
from typing import Set, List

class IPBlocker:
    def __init__(self, chain_name: str = "AUTOBOT"):
        self.chain_name = chain_name
        self.init_iptables()
    
    def init_iptables(self) -> None:
        """Initialise la chaîne iptables si elle n'existe pas."""
        try:
            result = subprocess.run(
                ["iptables", "-L", self.chain_name], 
                capture_output=True, 
                text=True
            )
            
            if "No chain/target/match by that name" in result.stderr:
                subprocess.run(["iptables", "-N", self.chain_name])
                
                subprocess.run(["iptables", "-A", "INPUT", "-j", self.chain_name])
                
                print(f"✅ [SECURITY] Chaîne iptables {self.chain_name} créée et ajoutée à INPUT")
        except Exception as e:
            print(f"❌ [SECURITY] Erreur lors de l'initialisation d'iptables: {str(e)}")
    
    def block_ip(self, ip: str) -> bool:
        """Bloque une IP avec iptables."""
        try:
            result = subprocess.run(
                ["iptables", "-C", self.chain_name, "-s", ip, "-j", "DROP"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                subprocess.run(["iptables", "-A", self.chain_name, "-s", ip, "-j", "DROP"])
                print(f"✅ [SECURITY] IP {ip} bloquée avec iptables")
            return True
        except Exception as e:
            print(f"❌ [SECURITY] Erreur lors du blocage de l'IP {ip}: {str(e)}")
            return False
    
    def unblock_ip(self, ip: str) -> bool:
        """Débloque une IP."""
        try:
            subprocess.run(["iptables", "-D", self.chain_name, "-s", ip, "-j", "DROP"])
            print(f"✅ [SECURITY] IP {ip} débloquée")
            return True
        except Exception as e:
            print(f"❌ [SECURITY] Erreur lors du déblocage de l'IP {ip}: {str(e)}")
            return False
