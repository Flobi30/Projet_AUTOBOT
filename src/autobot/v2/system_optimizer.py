"""
System Optimizer — Optimisation de bas niveau pour Linux (Hetzner CX33).
Gère le CPU Pinning et la priorité Real-Time (SCHED_FIFO).
"""

import os
import sys
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class SystemOptimizer:
    """
    Optimise les performances système pour le trading haute fréquence.
    Note : SCHED_FIFO nécessite généralement des privilèges root ou CAP_SYS_NICE.
    """

    @staticmethod
    def set_cpu_affinity(cpus: List[int]) -> bool:
        """
        Épingle le processus actuel sur des cœurs CPU spécifiques.
        Uniquement disponible sur Linux.
        """
        if sys.platform != "linux":
            logger.debug("CPU Pinning ignoré (non-Linux)")
            return False
        
        try:
            os.sched_setaffinity(0, cpus)
            logger.info(f"✅ CPU Affinity fixée sur les cœurs : {cpus}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Impossible de fixer l'affinity CPU : {e}")
            return False

    @staticmethod
    def set_realtime_priority(priority: int = 50) -> bool:
        """
        Active la priorité SCHED_FIFO pour le processus actuel.
        Uniquement disponible sur Linux.
        """
        if sys.platform != "linux":
            logger.debug("Priorité Real-time ignorée (non-Linux)")
            return False

        try:
            # Importation locale car non disponible sur Windows
            import sched
            param = os.sched_param(priority)
            os.sched_setscheduler(0, os.SCHED_FIFO, param)
            logger.info(f"🚀 Priorité Real-time activée (SCHED_FIFO, niveau {priority})")
            return True
        except PermissionError:
            logger.warning("⚠️ Permission refusée pour SCHED_FIFO. Essayez sudo ou setcap.")
            return False
        except Exception as e:
            logger.warning(f"❌ Erreur lors de l'activation de SCHED_FIFO : {e}")
            return False

    @staticmethod
    def optimize_for_hetzner():
        """
        Configuration recommandée pour un CX33 (4 vCPUs).
        - Trading/Event Loop sur CPU 1
        - ML/Inference sur CPU 2
        """
        logger.info("🛠️ Optimisation système pour Hetzner CX33...")
        
        # On épingle par défaut sur le premier cœur pour la boucle principale
        # L'épinglage granulaire peut être fait au niveau des workers
        SystemOptimizer.set_cpu_affinity([0, 1])
        SystemOptimizer.set_realtime_priority(80)
