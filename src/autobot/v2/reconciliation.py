"""
Reconciliation - Synchronisation état local avec Kraken

PHASE 3: Ce module assure que l'état local du bot (positions, capital, ordres)
est toujours synchronisé avec la réalité de l'exchange Kraken.

Problèmes résolus:
- Divergence après crash (positions fermées sur Kraken mais ouvertes localement)
- Ordres orphelins (partiellement remplis, jamais complétés)
- Capital tracké différent du capital réel
- Double-achat dû à des signaux non reconnus comme exécutés
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Thread, Event, Lock

from .order_executor import OrderExecutor, OrderStatus
from .instance import TradingInstance

logger = logging.getLogger(__name__)


@dataclass
class Divergence:
    """Représente une divergence entre état local et Kraken"""
    type: str  # 'orphan_local', 'orphan_kraken', 'partial_fill', 'price_mismatch'
    position_id: Optional[str]
    kraken_txid: Optional[str]
    details: Dict[str, Any]
    severity: str  # 'critical', 'warning', 'info'


class ReconciliationManager:
    """
    Gestionnaire de réconciliation état local ↔ Kraken.
    
    Responsabilités:
    1. Au démarrage: comparer positions locales vs positions Kraken
    2. Détecter divergences (positions orphelines, manquantes)
    3. Corriger état local si nécessaire
    4. Réconciliation périodique (toutes les heures)
    5. Rapport de santé du système
    """
    
    def __init__(
        self,
        order_executor: OrderExecutor,
        instances: Dict[str, TradingInstance],
        check_interval: int = 3600  # 1 heure
    ):
        self.order_executor = order_executor
        self.instances = instances
        self.check_interval = check_interval
        
        self._running = False
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._lock = Lock()
        
        # Statistiques
        self._reconciliation_count = 0
        self._last_reconciliation: Optional[datetime] = None
        
        logger.info("🔄 ReconciliationManager initialisé")
    
    def reconcile_all(self) -> List[Divergence]:
        """
        Lance une réconciliation complète de toutes les instances.
        
        Returns:
            Liste des divergences trouvées et corrigées
        """
        all_divergences = []
        
        logger.info("🔄 Lancement réconciliation complète...")
        
        for instance_id, instance in self.instances.items():
            try:
                divergences = self._reconcile_instance(instance)
                all_divergences.extend(divergences)
            except Exception as e:
                logger.exception(f"❌ Erreur réconciliation instance {instance_id}: {e}")
        
        self._reconciliation_count += 1
        self._last_reconciliation = datetime.now()
        
        if all_divergences:
            critical = len([d for d in all_divergences if d.severity == 'critical'])
            warnings = len([d for d in all_divergences if d.severity == 'warning'])
            logger.warning(f"⚠️ Réconciliation terminée: {critical} critiques, {warnings} avertissements")
        else:
            logger.info("✅ Réconciliation terminée: aucune divergence")
        
        return all_divergences
    
    def _reconcile_instance(self, instance: TradingInstance) -> List[Divergence]:
        """
        Réconciliation d'une instance spécifique.
        
        Args:
            instance: Instance à réconcilier
            
        Returns:
            Liste des divergences
        """
        divergences = []
        instance_id = instance.id
        
        logger.info(f"   Réconciliation instance {instance_id}...")
        
        # 1. Récupère positions locales ouvertes
        local_positions = instance.get_positions_snapshot()
        local_open = [p for p in local_positions if p.get('status') == 'open']
        
        # 2. Récupère positions/ordres ouverts sur Kraken
        kraken_orders = self._get_kraken_orders(instance.config.symbol)
        
        # 3. Détecte positions locales orphelines (ouvertes localement mais pas sur Kraken)
        for pos in local_open:
            pos_id = pos.get('id')
            txid = pos.get('txid')  # TXID de l'ordre d'achat sur Kraken
            
            if not txid:
                # Position créée sans ordre Kraken → simulation → à fermer
                divergence = Divergence(
                    type='orphan_local',
                    position_id=pos_id,
                    kraken_txid=None,
                    details={'reason': 'Position sans TXID Kraken (simulation ?)'},
                    severity='critical'
                )
                divergences.append(divergence)
                
                # Correction: fermer la position locale
                logger.warning(f"      🚨 Position orpheline détectée: {pos_id} - Fermeture locale")
                instance.close_position(pos_id, pos.get('buy_price', 0))
                continue
            
            # Vérifie si l'ordre existe encore sur Kraken
            kraken_status = self.order_executor.get_order_status(txid)
            
            if kraken_status is None:
                # Ordre inexistant sur Kraken → probablement exécuté puis vendu
                divergence = Divergence(
                    type='orphan_local',
                    position_id=pos_id,
                    kraken_txid=txid,
                    details={'reason': 'Ordre achat inexistant sur Kraken'},
                    severity='warning'
                )
                divergences.append(divergence)
                
                # Vérifier si la position a été vendue (via ClosedOrders)
                if self._check_if_sold_on_kraken(txid, instance.config.symbol):
                    logger.warning(f"      Position {pos_id} vendue sur Kraken mais ouverte localement - Fermeture")
                    instance.close_position(pos_id, self._get_last_price(instance.config.symbol))
            
            elif kraken_status.status == 'closed':
                # Ordre fermé sur Kraken → position devrait être ouverte
                # Vérifier si elle a été vendue depuis
                if self._check_if_sold_on_kraken(txid, instance.config.symbol):
                    divergence = Divergence(
                        type='orphan_local',
                        position_id=pos_id,
                        kraken_txid=txid,
                        details={'reason': 'Position vendue sur Kraken mais ouverte localement'},
                        severity='critical'
                    )
                    divergences.append(divergence)
                    
                    logger.warning(f"      🚨 Position {pos_id} vendue sur Kraken - Fermeture locale")
                    sell_price = self._get_average_sell_price(txid, instance.config.symbol)
                    instance.close_position(pos_id, sell_price)
            
            elif kraken_status.status == 'open':
                # Ordre toujours ouvert sur Kraken → anormal pour une position
                logger.debug(f"      Ordre {txid[:8]}... toujours ouvert (pas encore exécuté ?)")
        
        # 4. Vérifie capital tracké vs réel
        capital_divergence = self._check_capital_divergence(instance)
        if capital_divergence:
            divergences.append(capital_divergence)
        
        return divergences
    
    def _get_kraken_orders(self, symbol: str) -> Dict[str, OrderStatus]:
        """
        Récupère tous les ordres ouverts sur Kraken pour un symbole.
        
        Returns:
            Dict {txid: OrderStatus}
        """
        # TODO: Implémenter récupération via OpenOrders + ClosedOrders récents
        # Pour l'instant, retourne dict vide (sera complété lors de l'intégration)
        return {}
    
    def _check_if_sold_on_kraken(self, buy_txid: str, symbol: str) -> bool:
        """
        Vérifie si une position achetée a été vendue sur Kraken.
        
        Args:
            buy_txid: TXID de l'ordre d'achat
            symbol: Paire trading
            
        Returns:
            True si vendue
        """
        # Récupère ClosedOrders récents et cherche une vente correspondante
        # Pour l'instant, retourne False (sera implémenté)
        return False
    
    def _get_average_sell_price(self, buy_txid: str, symbol: str) -> float:
        """
        Récupère le prix moyen de vente d'une position.
        
        Args:
            buy_txid: TXID de l'achat
            symbol: Paire trading
            
        Returns:
            Prix de vente ou prix actuel si non trouvé
        """
        # TODO: Implémenter via QueryTrades ou ClosedOrders
        return 0.0
    
    def _get_last_price(self, symbol: str) -> float:
        """Récupère le dernier prix connu pour un symbole."""
        # TODO: Récupérer depuis WebSocket ou API Ticker
        return 0.0
    
    def _check_capital_divergence(self, instance: TradingInstance) -> Optional[Divergence]:
        """
        Vérifie si le capital tracké diverge du capital réel sur Kraken.
        
        Returns:
            Divergence si écart significatif (> 1%), None sinon
        """
        # Récupère capital local
        local_capital = instance.get_current_capital()
        
        # Récupère capital réel depuis Kraken
        real_capital = self.order_executor._get_client().query_private('Balance')
        
        # Compare (à implémenter avec vraie logique)
        return None
    
    def _reconciliation_loop(self):
        """Boucle de réconciliation périodique."""
        logger.info("🔄 Boucle de réconciliation démarrée")
        
        # Réconciliation immédiate au démarrage
        self.reconcile_all()
        
        while self._running:
            try:
                # Attente jusqu'au prochain check
                if self._stop_event.wait(timeout=self.check_interval):
                    break
                
                # Réconciliation périodique
                self.reconcile_all()
                
            except Exception as e:
                logger.exception(f"❌ Erreur boucle réconciliation: {e}")
                if self._stop_event.wait(timeout=60):
                    break
        
        logger.info("🔄 Boucle de réconciliation arrêtée")
    
    def start(self):
        """Démarre la réconciliation périodique."""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._monitor_thread = Thread(target=self._reconciliation_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info("✅ ReconciliationManager démarré")
    
    def stop(self):
        """Arrête la réconciliation."""
        if not self._running:
            return
        
        logger.info("🛑 Arrêt ReconciliationManager...")
        self._running = False
        self._stop_event.set()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        
        logger.info("✅ ReconciliationManager arrêté")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de réconciliation."""
        return {
            'reconciliation_count': self._reconciliation_count,
            'last_reconciliation': self._last_reconciliation.isoformat() if self._last_reconciliation else None,
            'check_interval': self.check_interval,
            'is_running': self._running
        }
