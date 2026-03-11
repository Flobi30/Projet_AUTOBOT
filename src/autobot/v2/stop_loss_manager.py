"""
StopLossManager - Gestion et synchronisation des stop-loss Kraken

PHASE 2: Ce module assure que les stop-loss posés sur Kraken sont synchronisés
avec l'état local du bot. Si un stop-loss se déclenche sur Kraken pendant que
le bot est offline, la position sera correctement marquée comme fermée au redémarrage.
"""

import logging
import time
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from threading import Thread, Event, Lock

from .order_executor import OrderExecutor, OrderStatus

logger = logging.getLogger(__name__)


class StopLossManager:
    """
    Gestionnaire de stop-loss Kraken.
    
    Responsabilités:
    1. Surveiller les stop-loss déclenchés sur Kraken
    2. Synchroniser fermetures avec les positions locales
    3. Annuler stop-loss lors de fermeture manuelle
    4. Réconciliation au démarrage (positions fermées pendant offline)
    """
    
    def __init__(self, order_executor: OrderExecutor, check_interval: int = 30):
        """
        Args:
            order_executor: Exécuteur d'ordres pour communiquer avec Kraken
            check_interval: Intervalle de vérification en secondes
        """
        self.order_executor = order_executor
        self.check_interval = check_interval
        
        self._running = False
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._lock = Lock()
        
        # Cache des stop-loss surveillés: {txid: position_id}
        self._monitored_stop_losses: Dict[str, str] = {}
        
        logger.info("🛡️ StopLossManager initialisé")
    
    def register_stop_loss(self, txid: str, position_id: str) -> bool:
        """
        Enregistre un stop-loss à surveiller.
        
        Args:
            txid: TXID de l'ordre stop-loss sur Kraken
            position_id: ID local de la position protégée
            
        Returns:
            True si enregistré
        """
        with self._lock:
            self._monitored_stop_losses[txid] = position_id
        
        logger.info(f"🛡️ Stop-loss enregistré: {txid[:8]}... → position {position_id}")
        return True
    
    def unregister_stop_loss(self, txid: str) -> bool:
        """
        Retire un stop-loss de la surveillance (fermeture manuelle).
        
        Args:
            txid: TXID du stop-loss
            
        Returns:
            True si trouvé et retiré
        """
        with self._lock:
            if txid in self._monitored_stop_losses:
                del self._monitored_stop_losses[txid]
                logger.info(f"🗑️ Stop-loss retiré: {txid[:8]}...")
                return True
        return False
    
    def check_stop_loss(self, txid: str) -> Tuple[bool, Optional[OrderStatus]]:
        """
        Vérifie le statut d'un stop-loss sur Kraken.
        
        Args:
            txid: TXID de l'ordre
            
        Returns:
            (triggered, order_status)
            triggered: True si le stop-loss s'est déclenché
        """
        status = self.order_executor.get_order_status(txid)
        
        if status is None:
            logger.warning(f"⚠️ Impossible de récupérer statut stop-loss {txid[:8]}...")
            return False, None
        
        # Vérifier si déclenché (closed = exécuté)
        if status.status == 'closed':
            logger.info(f"🚨 Stop-loss déclenché: {txid[:8]}... exécuté {status.volume_exec}/{status.volume}")
            return True, status
        
        elif status.status == 'canceled':
            logger.info(f"ℹ️ Stop-loss annulé: {txid[:8]}...")
            return False, status
        
        # Toujours ouvert
        return False, status
    
    def reconcile_positions(self, positions: List[Any]) -> List[Tuple[str, OrderStatus]]:
        """
        Réconciliation au démarrage: vérifie tous les stop-loss des positions ouvertes.
        
        Args:
            positions: Liste des positions ouvertes (avec stop_loss_txid)
            
        Returns:
            Liste des positions où stop-loss a été déclenché: [(position_id, order_status), ...]
        """
        triggered = []
        
        logger.info(f"🔍 Réconciliation stop-loss: {len(positions)} position(s) à vérifier")
        
        for position in positions:
            txid = getattr(position, 'stop_loss_txid', None)
            if not txid:
                continue
            
            was_triggered, status = self.check_stop_loss(txid)
            
            if was_triggered and status:
                triggered.append((position.id, status))
                logger.warning(f"🚨 Position {position.id} a été fermée par stop-loss sur Kraken")
            else:
                # Ré-enregistrer pour surveillance continue
                self.register_stop_loss(txid, position.id)
        
        if triggered:
            logger.warning(f"   {len(triggered)} position(s) fermée(s) pendant offline")
        else:
            logger.info(f"   Tous les stop-loss sont en attente")
        
        return triggered
    
    def cancel_stop_loss_for_position(self, position: Any) -> bool:
        """
        Annule le stop-loss d'une position (lors de fermeture manuelle).
        
        Args:
            position: Position dont il faut annuler le stop-loss
            
        Returns:
            True si annulé ou inexistant
        """
        txid = getattr(position, 'stop_loss_txid', None)
        if not txid:
            return True
        
        # Annule sur Kraken
        success = self.order_executor.cancel_order(txid)
        
        if success:
            self.unregister_stop_loss(txid)
            logger.info(f"🚫 Stop-loss annulé pour position {position.id}")
        else:
            logger.error(f"❌ Échec annulation stop-loss pour position {position.id}")
        
        return success
    
    def _monitor_loop(self):
        """Boucle de surveillance continue des stop-loss."""
        logger.info("🛡️ Surveillance stop-loss démarrée")
        
        while self._running:
            try:
                # Copie pour éviter modification pendant itération
                with self._lock:
                    monitored = dict(self._monitored_stop_losses)
                
                for txid, position_id in monitored.items():
                    try:
                        was_triggered, status = self.check_stop_loss(txid)
                        
                        if was_triggered:
                            # Notifier via callback si défini
                            if self._on_stop_loss_triggered:
                                self._on_stop_loss_triggered(position_id, status)
                            
                            # Retirer de la surveillance
                            self.unregister_stop_loss(txid)
                    
                    except Exception as e:
                        logger.exception(f"❌ Erreur vérification stop-loss {txid[:8]}...: {e}")
                
                # Attente avant prochain check
                if self._stop_event.wait(timeout=self.check_interval):
                    break
                    
            except Exception as e:
                logger.exception(f"❌ Erreur boucle surveillance stop-loss: {e}")
                if self._stop_event.wait(timeout=5):
                    break
        
        logger.info("🛡️ Surveillance stop-loss arrêtée")
    
    def start(self, on_stop_loss_triggered: Optional[callable] = None):
        """
        Démarre la surveillance continue.
        
        Args:
            on_stop_loss_triggered: Callback(position_id, order_status) appelé quand un SL se déclenche
        """
        if self._running:
            return
        
        self._running = True
        self._on_stop_loss_triggered = on_stop_loss_triggered
        self._stop_event.clear()
        
        self._monitor_thread = Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info("✅ StopLossManager démarré")
    
    def stop(self):
        """Arrête la surveillance."""
        if not self._running:
            return
        
        logger.info("🛑 Arrêt StopLossManager...")
        self._running = False
        self._stop_event.set()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        logger.info("✅ StopLossManager arrêté")
    
    def get_monitored_count(self) -> int:
        """Retourne le nombre de stop-loss surveillés."""
        with self._lock:
            return len(self._monitored_stop_losses)


# Singleton
_manager_instance: Optional[StopLossManager] = None
_manager_lock = Lock()


def get_stop_loss_manager(order_executor: Optional[OrderExecutor] = None) -> StopLossManager:
    """Retourne le StopLossManager (singleton)."""
    global _manager_instance
    
    with _manager_lock:
        if _manager_instance is None and order_executor is not None:
            _manager_instance = StopLossManager(order_executor)
        return _manager_instance
