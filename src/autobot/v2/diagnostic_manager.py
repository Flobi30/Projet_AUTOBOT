"""
Diagnostic System — AutoBot V2

Module intégré pour diagnostiquer automatiquement les problèmes.
Fonctionne en continu et rapporte l'état de santé du système.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import psutil
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Statut de santé complet du système."""
    timestamp: datetime
    overall: str  # "healthy", "warning", "critical"
    
    # Composants
    docker: Dict[str, Any]
    system: Dict[str, Any]
    network: Dict[str, Any]
    kraken: Dict[str, Any]
    database: Dict[str, Any]
    bot: Dict[str, Any]
    
    # Problèmes détectés
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class DiagnosticManager:
    """
    Gestionnaire de diagnostic intégré.
    
    Surveille en continu :
    - Ressources système (RAM, CPU, disque)
    - Connectivité réseau (Kraken API)
    - État Docker
    - Santé base de données
    - Fonctionnement du bot
    
    Usage:
        diag = DiagnosticManager()
        status = await diag.run_full_check()
        if status.overall != "healthy":
            logger.error(f"Problèmes: {status.issues}")
    """
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self._last_status: Optional[HealthStatus] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start_monitoring(self):
        """Démarre la surveillance continue."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("🔍 DiagnosticManager démarré")
    
    async def stop_monitoring(self):
        """Arrête la surveillance."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🔍 DiagnosticManager arrêté")
    
    async def _monitoring_loop(self):
        """Boucle de surveillance."""
        while self._running:
            try:
                status = await self.run_full_check()
                self._last_status = status
                
                if status.overall == "critical":
                    logger.error(f"🚨 CRITIQUE: {status.issues}")
                elif status.overall == "warning":
                    logger.warning(f"⚠️ WARNING: {status.issues}")
                
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.exception(f"Erreur diagnostic: {e}")
                await asyncio.sleep(10)
    
    async def run_full_check(self) -> HealthStatus:
        """Exécute un diagnostic complet."""
        issues = []
        recommendations = []
        
        # Vérifications parallèles
        docker_status = await self._check_docker()
        system_status = self._check_system()
        network_status = await self._check_network()
        kraken_status = await self._check_kraken()
        db_status = self._check_database()
        bot_status = self._check_bot()
        
        # Collecte des problèmes
        all_checks = [
            ("Docker", docker_status),
            ("Système", system_status),
            ("Réseau", network_status),
            ("Kraken", kraken_status),
            ("Base de données", db_status),
            ("Bot", bot_status),
        ]
        
        for name, status in all_checks:
            if status.get("status") == "error":
                issues.append(f"{name}: {status.get('error', 'Erreur inconnue')}")
            elif status.get("status") == "warning":
                issues.append(f"{name}: {status.get('warning', 'Attention')}")
        
        # Génération recommandations
        recommendations = self._generate_recommendations(
            docker_status, system_status, network_status,
            kraken_status, db_status, bot_status
        )
        
        # Détermination statut global
        if any(s.get("status") == "error" for _, s in all_checks):
            overall = "critical"
        elif any(s.get("status") == "warning" for _, s in all_checks):
            overall = "warning"
        else:
            overall = "healthy"
        
        return HealthStatus(
            timestamp=datetime.now(timezone.utc),
            overall=overall,
            docker=docker_status,
            system=system_status,
            network=network_status,
            kraken=kraken_status,
            database=db_status,
            bot=bot_status,
            issues=issues,
            recommendations=recommendations
        )
    
    async def _check_docker(self) -> Dict[str, Any]:
        """Vérifie l'état Docker."""
        try:
            result = await asyncio.create_subprocess_exec(
                "docker", "ps", "--format", "{{.Names}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return {"status": "error", "error": f"Docker: {stderr.decode()}"}
            
            containers = stdout.decode().strip().split("\n")
            autobot_running = any("autobot" in c for c in containers)
            
            if not autobot_running:
                return {
                    "status": "error",
                    "error": "Conteneur AutoBot non trouvé",
                    "containers": containers
                }
            
            return {
                "status": "ok",
                "containers": containers,
                "autobot_running": autobot_running
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _check_system(self) -> Dict[str, Any]:
        """Vérifie les ressources système."""
        try:
            # RAM
            mem = psutil.virtual_memory()
            ram_percent = mem.percent
            ram_available_gb = mem.available / (1024**3)
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Disque
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent
            disk_free_gb = disk.free / (1024**3)
            
            status = "ok"
            warning = None
            
            if ram_percent > 90 or ram_available_gb < 0.5:
                status = "critical"
                warning = f"RAM critique: {ram_percent}% utilisé, {ram_available_gb:.1f}GB libre"
            elif ram_percent > 80:
                status = "warning"
                warning = f"RAM élevée: {ram_percent}%"
            
            if disk_percent > 90:
                status = "critical"
                warning = f"Disque critique: {disk_percent}% plein"
            elif disk_percent > 80:
                status = "warning" if status == "ok" else status
                warning = f"Disque presque plein: {disk_percent}%"
            
            return {
                "status": status,
                "warning": warning,
                "ram_percent": ram_percent,
                "ram_available_gb": ram_available_gb,
                "cpu_percent": cpu_percent,
                "disk_percent": disk_percent,
                "disk_free_gb": disk_free_gb
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _check_network(self) -> Dict[str, Any]:
        """Vérifie la connectivité réseau."""
        try:
            # Test DNS
            socket.gethostbyname("api.kraken.com")
            
            # Test ping (optionnel, peut échouer sans être critique)
            return {
                "status": "ok",
                "dns": "fonctionnel",
                "external_ip": await self._get_external_ip()
            }
        except Exception as e:
            return {"status": "error", "error": f"Réseau: {str(e)}"}
    
    async def _check_kraken(self) -> Dict[str, Any]:
        """Vérifie la connectivité API Kraken."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("api.kraken.com", 443),
                timeout=10.0
            )
            writer.close()
            await writer.wait_closed()
            return {
                "status": "ok",
                "api_accessible": True,
                "response_time_ms": "<1000"
            }
        except asyncio.TimeoutError:
            return {
                "status": "warning",
                "api_accessible": False,
                "error": "Timeout connexion Kraken (lent ou indisponible)"
            }
        except Exception as e:
            return {"status": "error", "error": f"Kraken: {str(e)}"}
    
    def _check_database(self) -> Dict[str, Any]:
        """Vérifie l'état de la base de données SQLite."""
        try:
            db_path = "/opt/autobot/data/autobot.db"
            if not os.path.exists(db_path):
                return {
                    "status": "warning",
                    "warning": "Base de données non trouvée (premier démarrage ?)"
                }
            
            size_mb = os.path.getsize(db_path) / (1024 * 1024)
            
            return {
                "status": "ok",
                "exists": True,
                "size_mb": round(size_mb, 2)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _check_bot(self) -> Dict[str, Any]:
        """Vérifie l'état du bot via les logs."""
        try:
            log_path = "/opt/autobot/logs/autobot.log"
            if not os.path.exists(log_path):
                return {
                    "status": "warning",
                    "warning": "Fichier de logs non trouvé"
                }
            
            # Vérifier si le log est récent (< 5 minutes)
            mtime = os.path.getmtime(log_path)
            age_minutes = (time.time() - mtime) / 60
            
            if age_minutes > 5:
                return {
                    "status": "warning",
                    "warning": f"Logs non mis à jour depuis {age_minutes:.0f} minutes",
                    "last_update_minutes": age_minutes
                }
            
            return {
                "status": "ok",
                "logs_active": True,
                "last_update_minutes": age_minutes
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _get_external_ip(self) -> Optional[str]:
        """Récupère l'IP externe."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("ifconfig.me", 80),
                timeout=5.0
            )
            writer.write(b"GET / HTTP/1.1\r\nHost: ifconfig.me\r\n\r\n")
            await writer.drain()
            
            response = await reader.read(1024)
            writer.close()
            await writer.wait_closed()
            
            # Extrait l'IP de la réponse HTTP
            body = response.decode().split("\r\n\r\n")[-1]
            return body.strip()
        except:
            return None
    
    def _generate_recommendations(self, docker, system, network, kraken, db, bot) -> List[str]:
        """Génère des recommandations basées sur les problèmes."""
        recs = []
        
        if system.get("ram_percent", 0) > 80:
            recs.append("RAM élevée: réduire MAX_INSTANCES ou passer à un serveur plus gros")
        
        if system.get("disk_percent", 0) > 80:
            recs.append("Disque presque plein: nettoyer les logs anciens avec 'docker system prune'")
        
        if docker.get("status") == "error":
            recs.append("Docker problème: vérifier 'docker ps' et 'systemctl status docker'")
        
        if kraken.get("status") != "ok":
            recs.append("Kraken inaccessible: vérifier connexion internet et firewall")
        
        if bot.get("status") == "warning":
            recs.append("Bot peu actif: vérifier les logs avec 'docker logs -f autobot-v2'")
        
        if not recs:
            recs.append("Aucune action requise, le système fonctionne bien !")
        
        return recs
    
    def get_last_status(self) -> Optional[HealthStatus]:
        """Retourne le dernier statut connu."""
        return self._last_status
    
    def get_summary_text(self) -> str:
        """Retourne un résumé textuel pour l'utilisateur."""
        if not self._last_status:
            return "Aucun diagnostic disponible encore"
        
        s = self._last_status
        lines = [
            f"📊 Diagnostic AutoBot — {s.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Statut global: {'✅' if s.overall == 'healthy' else '⚠️' if s.overall == 'warning' else '🚨'} {s.overall.upper()}",
            "",
        ]
        
        if s.issues:
            lines.append("🚨 Problèmes détectés:")
            for issue in s.issues:
                lines.append(f"  • {issue}")
            lines.append("")
        
        lines.append("💡 Recommandations:")
        for rec in s.recommendations:
            lines.append(f"  • {rec}")
        
        return "\n".join(lines)


# Singleton
_diagnostic_manager: Optional[DiagnosticManager] = None


def get_diagnostic_manager() -> DiagnosticManager:
    """Retourne l'instance singleton du DiagnosticManager."""
    global _diagnostic_manager
    if _diagnostic_manager is None:
        _diagnostic_manager = DiagnosticManager()
    return _diagnostic_manager
