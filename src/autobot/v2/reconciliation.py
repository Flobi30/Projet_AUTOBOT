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

        # CORRECTION F3: Recalcule capital alloué pour corriger la dérive
        instance.recalculate_allocated_capital()

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
        CORRECTION C1: Implémente récupération des ordres sur Kraken.

        Returns:
            Dict {txid: OrderStatus}
        """
        orders = {}
        try:
            # Récupère ordres ouverts
            open_orders = self.order_executor._safe_api_call('OpenOrders')
            if open_orders[0] and 'result' in open_orders[1] and 'open' in open_orders[1]['result']:
                for txid, info in open_orders[1]['result']['open'].items():
                    orders[txid] = OrderStatus(
                        txid=txid,
                        status='open',
                        volume=float(info.get('vol', 0)),
                        volume_exec=float(info.get('vol_exec', 0)),
                        price=float(info.get('price', 0)) if info.get('price') else None,
                        avg_price=float(info.get('avg_price', 0)) if info.get('avg_price') else None,
                        fee=float(info.get('fee', 0))
                    )

            # Récupère ordres fermés récents (dernières 24h)
            closed_orders = self.order_executor.get_closed_orders(
                start_time=int(time.time()) - 86400  # 24h en arrière
            )
            for txid, info in closed_orders.items():
                orders[txid] = OrderStatus(
                    txid=txid,
                    status='closed',
                    volume=float(info.get('vol', 0)),
                    volume_exec=float(info.get('vol_exec', 0)),
                    price=float(info.get('price', 0)) if info.get('price') else None,
                    avg_price=float(info.get('avg_price', 0)) if info.get('avg_price') else None,
                    fee=float(info.get('fee', 0))
                )

        except Exception as e:
            logger.error(f"❌ Erreur récupération ordres Kraken: {e}")

        return orders

    def _check_if_sold_on_kraken(self, buy_txid: str, symbol: str) -> bool:
        """
        CORRECTION C1: Vérifie si une position a été vendue sur Kraken.
        """
        try:
            # Récupère l'ordre d'achat
            buy_status = self.order_executor.get_order_status(buy_txid)
            if not buy_status or buy_status.status != 'closed':
                return False  # Achat pas encore exécuté

            # Récupère ClosedOrders récents pour trouver une vente correspondante
            closed_orders = self.order_executor.get_closed_orders(
                start_time=int(time.time()) - 86400
            )

            for txid, info in closed_orders.items():
                # Vérifie si c'est un ordre de vente (type='sell')
                descr = info.get('descr', {})
                if descr.get('type') == 'sell' and descr.get('pair') == symbol:
                    # Vérifie si le volume correspond approximativement
                    vol = float(info.get('vol', 0))
                    if abs(vol - buy_status.volume_exec) < 0.0001:  # Tolérance
                        return True

            return False

        except Exception as e:
            logger.error(f"❌ Erreur vérification vente Kraken: {e}")
            return False

    def _get_average_sell_price(self, buy_txid: str, symbol: str) -> float:
        """
        CORRECTION C1: Récupère le prix moyen de vente.
        """
        try:
            closed_orders = self.order_executor.get_closed_orders(
                start_time=int(time.time()) - 86400
            )

            for txid, info in closed_orders.items():
                descr = info.get('descr', {})
                if descr.get('type') == 'sell' and descr.get('pair') == symbol:
                    avg_price = float(info.get('avg_price', 0))
                    if avg_price > 0:
                        return avg_price

            return 0.0

        except Exception as e:
            logger.error(f"❌ Erreur récupération prix vente: {e}")
            return 0.0

    def _get_last_price(self, symbol: str) -> float:
        """
        CORRECTION C1: Récupère le dernier prix via API Ticker.
        """
        try:
            # Utilise l'API publique Ticker
            response = self.order_executor._safe_api_call('Ticker', pair=symbol)
            if response[0] and 'result' in response[1]:
                pair_data = response[1]['result'].get(symbol, {})
                last_price = pair_data.get('c', [0])[0]  # Prix du dernier trade
                return float(last_price)
            return 0.0
        except Exception as e:
            logger.error(f"❌ Erreur récupération prix: {e}")
            return 0.0

    def _check_capital_divergence(self, instance: TradingInstance) -> Optional[Divergence]:
        """
        CORRECTION F3: Vérifie divergence capital tracké vs Kraken.
        """
        try:
            # Capital local
            local_capital = instance.get_current_capital()

            # Capital réel sur Kraken
            balances = self.order_executor.get_balance()
            eur_balance = balances.get('ZEUR', 0.0)
            btc_balance = balances.get('XXBT', 0.0)

            # Récupère prix BTC pour estimer valeur
            btc_price = self._get_last_price('XXBTZEUR')
            btc_value_eur = btc_balance * btc_price if btc_price > 0 else 0

            real_capital = eur_balance + btc_value_eur

            # Compare
            diff = abs(local_capital - real_capital)
            diff_pct = (diff / local_capital * 100) if local_capital > 0 else 0

            if diff_pct > 1.0:  # Seuil 1%
                return Divergence(
                    type='capital_mismatch',
                    position_id=None,
                    kraken_txid=None,
                    details={
                        'local_capital': local_capital,
                        'real_capital': real_capital,
                        'difference': diff,
                        'difference_pct': diff_pct
                    },
                    severity='critical'
                )

            return None

        except Exception as e:
            logger.error(f"❌ Erreur vérification capital: {e}")
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
