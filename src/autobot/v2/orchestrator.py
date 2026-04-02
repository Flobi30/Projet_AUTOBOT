"""
Orchestrator - Gestionnaire central des instances de trading
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock, Thread, Event
import time

from .websocket_client import KrakenWebSocket, TickerData, WebSocketMultiplexer
from .validator import ValidatorEngine, ValidationResult, ValidationStatus
from .instance import TradingInstance
from .order_executor import OrderExecutor, get_order_executor
from .stop_loss_manager import StopLossManager, get_stop_loss_manager
from .reconciliation import ReconciliationManager
from .market_selector import MarketSelector, get_market_selector
from .risk_manager import get_risk_manager

logger = logging.getLogger(__name__)

def _get_available_capital_real(api_key: Optional[str] = None, api_secret: Optional[str] = None) -> float:
    """
    Récupère capital disponible depuis API Kraken.
    
    Args:
        api_key: Clé API Kraken (ou KRAKEN_API_KEY env var)
        api_secret: Secret API Kraken (ou KRAKEN_API_SECRET env var)
    
    Returns:
        Capital disponible en EUR (ZEUR), ou 0.0 en cas d'erreur ou clés non configurées.
        NOTE: 0.0 peut signifier "vraiment zéro" OU "erreur API". C'est le pattern fail-safe.
    """
    import os
    
    # Récupère clés depuis arguments ou env vars
    key = api_key or os.getenv('KRAKEN_API_KEY')
    secret = api_secret or os.getenv('KRAKEN_API_SECRET')
    
    if not key or not secret:
        logger.warning("⚠️ Clés API Kraken non configurées - retourne 0.0")
        return 0.0
    
    try:
        import krakenex
        
        # Crée client API avec timeout
        k = krakenex.API(key=key, secret=secret)
        k.session.timeout = 10  # CORRECTION: Timeout 10s pour éviter blocage
        
        # Appelle Balance
        response = k.query_private('Balance')
        
        if 'result' in response:
            balances = response['result']
            
            # Récupère EUR (ZEUR sur Kraken)
            eur_balance = float(balances.get('ZEUR', 0))
            
            # Debug log uniquement (sécurité: pas de balance en INFO)
            btc_balance = float(balances.get('XXBT', 0))
            logger.debug(f"💰 Balance Kraken - EUR: {eur_balance:.2f}€, BTC: {btc_balance:.6f}")
            
            return eur_balance
        else:
            # CORRECTION: Masque détails erreur (sécurité), log debug séparé
            logger.error("❌ Erreur API Kraken Balance")
            if logger.isEnabledFor(logging.DEBUG):
                error_detail = response.get('error', ['Unknown'])
                logger.debug(f"Détail erreur Kraken: {error_detail}")
            return 0.0
            
    except ImportError:
        logger.error("❌ Module 'krakenex' non installé. Run: pip install krakenex")
        return 0.0
    except Exception as e:
        logger.exception(f"❌ Exception récupération balance Kraken: {e}")
        return 0.0


@dataclass(slots=True)
class InstanceConfig:
    """Configuration d'une instance"""
    name: str
    symbol: str
    strategy: str  # 'grid', 'trend', 'breakout'
    initial_capital: float
    leverage: int = 1  # 1, 2, 3...
    tp_sl_config: Dict = field(default_factory=dict)
    grid_config: Optional[Dict] = None
    

class Orchestrator:
    """
    Orchestrateur principal AUTOBOT V2.
    
    Gère:
    - Multi-instances dynamiques
    - Distribution des données WebSocket
    - Validation des actions
    - Spin-off automatique
    - Monitoring global
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret

        # CORRECTION CRITIQUE: Initialise les composants d'exécution réelle
        # OrderExecutor pour passer les ordres sur Kraken
        self.order_executor = get_order_executor(api_key, api_secret)

        # CORRECTION CRITIQUE: StopLossManager pour surveiller les SL sur Kraken
        self.stop_loss_manager = get_stop_loss_manager(self.order_executor)

        # WebSocket Kraken — OPTIMISATION: Multiplexeur (1 connexion pour N paires)
        self.ws_multiplexer = WebSocketMultiplexer(api_key, api_secret)
        # Alias de compatibilité (get_last_price, is_connected, etc.)
        self.ws_client = self.ws_multiplexer

        # Validator Engine
        self.validator = ValidatorEngine()

        # Instances
        self._instances: Dict[str, TradingInstance] = {}
        self._instance_lock = Lock()

        # CORRECTION CRITIQUE: ReconciliationManager (sera initialisé quand instances créées)
        self.reconciliation_manager: Optional[ReconciliationManager] = None

        # Configuration globale
        # Progressif : démarrer avec 5, monter à 50 selon capital
        self.config = {
            'max_instances': 50,  # Hard limit sécurité (configurable, progressif jusqu'à 50)
            'spin_off_threshold': 2000.0,
            'leverage_threshold': 1000.0,
            'check_interval': 30,  # minutes
            'max_drawdown_global': 0.30  # 30%
        }

        # État
        self.running = False
        self._stop_event = Event()  # CORRECTION: Event pour arrêt propre
        self._main_thread: Optional[Thread] = None
        self._start_time: Optional[datetime] = None

        # Callbacks
        self._on_instance_created: Optional[Callable] = None
        self._on_instance_spinoff: Optional[Callable] = None
        self._on_alert: Optional[Callable] = None

        # CORRECTION E6: Circuit breaker callback
        self._setup_circuit_breaker()
        
        # FEATURE: Market selector pour auto-sélection
        self.market_selector = get_market_selector(self)

        logger.info("🎛️ Orchestrator initialisé")

    def create_instance_auto(self, parent_instance_id: Optional[str] = None) -> Optional[TradingInstance]:
        """
        FEATURE: Crée une instance sur le meilleur marché disponible.
        Sélection automatique basée sur l'analyse des marchés.
        
        Args:
            parent_instance_id: ID instance parente (pour spin-off) ou None
            
        Returns:
            Instance créée ou None si pas de marché approprié
        """
        logger.info("🎯 Création instance avec auto-sélection du marché...")
        
        # Utilise le market selector pour choisir le meilleur marché
        selection = self.market_selector.select_market_for_spinoff(parent_instance_id or "auto")
        
        if not selection:
            logger.warning("⚠️ Aucun marché approprié trouvé")
            return None
        
        # Crée la configuration adaptée
        config = InstanceConfig(
            name=f"Auto-{selection.symbol.replace('/', '-')} ({selection.strategy})",
            symbol=selection.symbol,
            strategy=selection.strategy,
            initial_capital=0,  # Sera calculé par capital_allocation
            leverage=1,
            grid_config={
                'range_percent': 7.0 if selection.market_type.value == 'crypto' else 1.0,
                'num_levels': 15
            }
        )
        
        # Crée l'instance
        instance = self.create_instance(config)
        
        if instance:
            logger.info(f"✅ Instance auto-créée: {instance.id}")
            logger.info(f"   Marché: {selection.symbol} ({selection.market_type.value})")
            logger.info(f"   Raison: {selection.reason}")
        
        return instance

    def _setup_circuit_breaker(self):
        """Configure le circuit breaker sur OrderExecutor"""
        def on_circuit_breaker():
            logger.error("🚨 CIRCUIT BREAKER: Arrêt d'urgence de toutes les instances!")
            self.emergency_stop_all()

        self.order_executor.set_circuit_breaker_callback(on_circuit_breaker)
    
    def create_instance(self, config: InstanceConfig) -> Optional[TradingInstance]:
        """
        Crée une nouvelle instance de trading.
        
        Args:
            config: Configuration de l'instance
            
        Returns:
            Instance créée ou None si échec
        """
        with self._instance_lock:
            # Check limite globale
            if len(self._instances) >= self.config['max_instances']:
                logger.warning(f"⚠️ Limite instances atteinte: {self.config['max_instances']}")
                return None
            
            # Crée l'instance
            instance_id = str(uuid.uuid4())[:8]
            instance = TradingInstance(
                instance_id=instance_id,
                config=config,
                orchestrator=self,
                order_executor=self.order_executor  # CORRECTION CRITIQUE: Passe l'OrderExecutor
            )
            
            self._instances[instance_id] = instance

            # Warning si approche du max instances
            instance_count = len(self._instances)
            if instance_count > 20:
                logger.warning(
                    f"⚠️ Approche des 50 instances ({instance_count} actives) "
                    f"— vérifier ressources VPS"
                )

            # Subscribe aux données de marché via multiplexeur (1 connexion pour toutes les paires)
            # CORRECTION: Stocker callback pour pouvoir le retirer plus tard
            instance._ws_callback = lambda data, inst=instance: inst.on_price_update(data)
            self.ws_multiplexer.subscribe(config.symbol, instance._ws_callback)
            
            logger.info(f"✅ Instance créée: {instance_id} ({config.name}) - Capital: {config.initial_capital:.2f}€")
            
            if self._on_instance_created:
                self._on_instance_created(instance)
            
            return instance
    
    def remove_instance(self, instance_id: str) -> bool:
        """Supprime une instance"""
        with self._instance_lock:
            if instance_id not in self._instances:
                return False
            
            # Retire l'instance du dictionnaire
            instance = self._instances.pop(instance_id)
            
        # CORRECTION: Unsubscribe et stop EN DEHORS du lock pour éviter deadlock
        if hasattr(instance, '_ws_callback'):
            self.ws_multiplexer.unsubscribe(instance.config.symbol, instance._ws_callback)
        
        instance.stop()  # Peut bloquer jusqu'à 60s
        logger.info(f"🗑️ Instance supprimée: {instance_id}")
        return True
    
    def check_spin_off(self, parent_instance: TradingInstance) -> Optional[TradingInstance]:
        """
        Vérifie si spin-off possible et l'exécute si OK.
        
        FEATURE: Utilise l'auto-sélection du marché pour diversifier.
        
        Args:
            parent_instance: Instance mère potentielle
            
        Returns:
            Nouvelle instance créée ou None
        """
        capital = parent_instance.get_current_capital()
        
        context = {
            'capital': capital,
            'threshold': self.config['spin_off_threshold'],
            'available_capital': self._get_available_capital(),
            'min_capital': 500.0,
            'instance_count': len(self._instances),
            'max_instances': self.config['max_instances'],
            'volatility': parent_instance.get_volatility(),
            'max_volatility': 0.10
        }
        
        result = self.validator.validate('spin_off', context)
        
        if result.status == ValidationStatus.GREEN:
            # FEATURE: Auto-sélection du marché pour spin-off
            new_instance = self.create_instance_auto(parent_instance.id)
            
            if new_instance:
                parent_instance.record_spin_off(500.0)
                logger.info(f"🔄 Spin-off réussi: {parent_instance.id} → {new_instance.id}")
                
                if self._on_instance_spinoff:
                    self._on_instance_spinoff(parent_instance, new_instance)
                
                return new_instance
        else:
            logger.debug(f"⏳ Spin-off bloqué pour {parent_instance.id}: {result.message}")
        
        return None
    
    def check_leverage_activation(self, instance: TradingInstance) -> bool:
        """Vérifie si levier peut être activé"""
        capital = instance.get_current_capital()
        
        if capital < self.config['leverage_threshold']:
            return False
        
        context = {
            'capital': capital,
            'threshold': self.config['leverage_threshold'],
            'win_streak': instance.get_win_streak(),
            'min_win_streak': 5,
            'drawdown': instance.get_drawdown(),
            'max_drawdown': 0.10,
            'trend': instance.detect_trend()
        }
        
        result = self.validator.validate('leverage', context)
        
        if result.status in (ValidationStatus.GREEN, ValidationStatus.YELLOW):
            if instance.activate_leverage(2):  # x2
                logger.info(f"⚡ Levier x2 activé sur {instance.id}")
                return True
        
        return False
    
    def _get_available_capital(self) -> float:
        """Calcule capital disponible pour nouvelle instance via API Kraken"""
        # CORRECTION: Passe les clés API à la fonction
        return _get_available_capital_real(self.api_key, self.api_secret)
    
    def _main_loop(self):
        """Boucle principale de l'orchestrateur"""
        logger.info("🚀 Orchestrator main loop démarré")
        
        while self.running:
            try:
                loop_start = time.time()
                
                with self._instance_lock:
                    instances = list(self._instances.values())
                
                for instance in instances:
                    if not instance.is_running():
                        continue
                    
                    # Check spin-off
                    self.check_spin_off(instance)
                    
                    # Check levier
                    if instance.config.leverage == 1:
                        self.check_leverage_activation(instance)
                    
                    # Check santé instance
                    if instance.get_drawdown() > self.config['max_drawdown_global']:
                        logger.error(f"🚨 Drawdown critique sur {instance.id}: {instance.get_drawdown():.2%}")
                        instance.emergency_stop()
                        
                        if self._on_alert:
                            self._on_alert('CRITICAL_DRAWDOWN', instance)
                
                # Check global
                self._check_global_health()
                
                # Attente avant prochain check
                elapsed = time.time() - loop_start
                sleep_time = max(0, self.config['check_interval'] * 60 - elapsed)
                
                # CORRECTION: Utiliser Event.wait() pour arrêt propre
                if sleep_time > 0:
                    if self._stop_event.wait(timeout=sleep_time):
                        break  # Arrêt demandé
                    
            except Exception as e:
                logger.error(f"❌ Erreur main loop: {e}")
                # CORRECTION: Utiliser Event.wait() au lieu de sleep fixe
                if self._stop_event.wait(timeout=60):
                    break  # Arrêt demandé
    
    def _check_global_health(self):
        """Vérifie santé globale du système"""
        # Check connexion WebSocket
        if not self.ws_client.is_connected():
            logger.warning("🔌 WebSocket déconnecté, tentative reconnexion...")
            try:
                self.ws_client.connect()
            except Exception as e:
                logger.error(f"❌ Échec reconnexion WebSocket: {e}")

        # DISJONCTEUR: Vérification PF global < 1.2
        with self._instance_lock:
            active_instances = [
                inst for inst in self._instances.values() if inst.is_running()
            ]
        if active_instances:
            risk_manager = get_risk_manager()
            risk_manager.set_orchestrator(self)
            risk_manager.check_global_risk(active_instances)
    
    def start(self):
        """Démarre l'orchestrateur"""
        if self.running:
            logger.warning("⚠️ Orchestrator déjà démarré")
            return

        self.running = True
        self._start_time = datetime.now()

        # Connexion WebSocket (multiplexeur — 1 connexion pour toutes les paires)
        self.ws_multiplexer.connect()

        # CORRECTION CRITIQUE: Démarre StopLossManager avec callback pour notifier instances
        self.stop_loss_manager.start(
            on_stop_loss_triggered=self._on_stop_loss_triggered
        )
        logger.info("🛡️ StopLossManager démarré")

        # CORRECTION CRITIQUE: Initialise et démarre ReconciliationManager
        with self._instance_lock:
            instances_dict = dict(self._instances)
        self.reconciliation_manager = ReconciliationManager(
            order_executor=self.order_executor,
            instances=instances_dict
        )
        self.reconciliation_manager.start()
        logger.info("🔄 ReconciliationManager démarré")

        # CORRECTION: Copier instances sous lock, démarrer hors lock
        with self._instance_lock:
            instances_to_start = list(self._instances.values())

        for instance in instances_to_start:
            instance.start()

        # Boucle principale
        self._main_thread = Thread(target=self._main_loop, daemon=True)
        self._main_thread.start()

        logger.info("✅ Orchestrator démarré")

    def _on_stop_loss_triggered(self, position_id: str, order_status: Any):
        """
        CORRECTION CRITIQUE: Callback quand un stop-loss se déclenche sur Kraken.
        Notifie l'instance concernée pour fermer la position localement.
        """
        # Trouve l'instance qui a cette position
        with self._instance_lock:
            for instance in self._instances.values():
                # Vérifie si l'instance a cette position
                positions = instance.get_positions_snapshot()
                for pos in positions:
                    if pos.get('id') == position_id:
                        # Calcule le prix de vente réel
                        sell_price = order_status.avg_price if order_status.avg_price else order_status.price
                        if sell_price:
                            # Notifie l'instance
                            instance.on_stop_loss_triggered(position_id, sell_price)
                        return
    
    def stop(self):
        """Arrête l'orchestrateur"""
        logger.info("🛑 Arrêt Orchestrator...")
        self.running = False
        self._stop_event.set()  # CORRECTION: Signaler arrêt au thread
        
        # CORRECTION: Copier instances sous lock, stop hors lock
        with self._instance_lock:
            instances_to_stop = list(self._instances.values())
        
        # Arrêt instances hors lock (peut bloquer 60s chacune)
        for instance in instances_to_stop:
            instance.stop()
        
        # Arrêt WebSocket (multiplexeur)
        self.ws_multiplexer.disconnect()

        # CORRECTION CRITIQUE: Arrêt StopLossManager
        if self.stop_loss_manager:
            self.stop_loss_manager.stop()

        # CORRECTION CRITIQUE: Arrêt ReconciliationManager
        if self.reconciliation_manager:
            self.reconciliation_manager.stop()

        # Attente thread principal
        if self._main_thread:
            self._main_thread.join(timeout=10)

        logger.info("✅ Orchestrator arrêté")
    
    def emergency_stop_all(self):
        """
        Arrêt d'urgence de TOUTES les instances.
        Déclenché par le disjoncteur (circuit breaker) quand conditions critiques.
        """
        logger.error("🚨🚨🚨 EMERGENCY STOP ALL — Arrêt de toutes les instances!")

        with self._instance_lock:
            instances_to_stop = list(self._instances.values())

        stopped = 0
        for instance in instances_to_stop:
            try:
                instance.emergency_stop()
                stopped += 1
            except Exception as e:
                logger.exception(f"❌ Erreur arrêt urgence {instance.id}: {e}")

        logger.error(f"🚨 Emergency stop: {stopped}/{len(instances_to_stop)} instances arrêtées")

        # Émet alerte
        if self._on_alert:
            self._on_alert('EMERGENCY_STOP_ALL', None)

    def get_status(self) -> Dict:
        """Retourne statut global"""
        # CORRECTION: Copier instances sous lock
        with self._instance_lock:
            instances_copy = list(self._instances.values())
            instance_count = len(self._instances)
        
        return {
            'running': self.running,
            'start_time': self._start_time,
            'uptime': datetime.now() - self._start_time if self._start_time else None,
            'instance_count': instance_count,
            'max_instances': self.config['max_instances'],
            'websocket_connected': self.ws_client.is_connected(),
            'instances': [
                {
                    'id': inst.id,
                    'name': inst.config.name,
                    'capital': inst.get_current_capital(),
                    'running': inst.is_running()
                }
                for inst in instances_copy
            ]
        }
    
    def set_callbacks(self,
                      on_instance_created: Optional[Callable] = None,
                      on_instance_spinoff: Optional[Callable] = None,
                      on_alert: Optional[Callable] = None):
        """Définit les callbacks"""
        self._on_instance_created = on_instance_created
        self._on_instance_spinoff = on_instance_spinoff
        self._on_alert = on_alert

    # =========================================================================
    # CORRECTION: Méthodes thread-safe pour l'API Dashboard
    # =========================================================================

    def get_status_safe(self) -> Dict:
        """
        CORRECTION: Version thread-safe de get_status pour l'API.
        Retourne une copie snapshot de l'état.
        """
        with self._instance_lock:
            instances_copy = list(self._instances.values())
            instance_count = len(self._instances)

        return {
            'running': self.running,
            'start_time': self._start_time,
            'instance_count': instance_count,
            'max_instances': self.config['max_instances'],
            'websocket_connected': self.ws_client.is_connected(),
            'instances': [
                {
                    'id': inst.id,
                    'name': inst.config.name,
                    'capital': inst.get_current_capital(),
                    'profit': inst.get_profit(),
                    'running': inst.is_running()
                }
                for inst in instances_copy
            ]
        }

    def get_instances_snapshot(self) -> List[Dict]:
        """
        CORRECTION: Version thread-safe pour l'API.
        Retourne une snapshot des instances (pas d'accès direct à _instances).
        """
        with self._instance_lock:
            instances_copy = list(self._instances.items())

        snapshot = []
        for inst_id, instance in instances_copy:
            try:
                inst_status = instance.get_status()
                snapshot.append({
                    'id': inst_id,
                    'name': inst_status['name'],
                    'capital': inst_status['current_capital'],
                    'profit': inst_status['total_profit'],
                    'status': inst_status['status'],
                    'strategy': inst_status['strategy'],
                    'open_positions': inst_status['open_positions_count']
                })
            except Exception as e:
                logger.error(f"❌ Erreur snapshot instance {inst_id}: {e}")

        return snapshot

    def get_instance_positions_snapshot(self, instance_id: str) -> Optional[List[Dict]]:
        """
        CORRECTION: Version thread-safe pour l'API.
        Retourne une snapshot des positions d'une instance.
        """
        with self._instance_lock:
            instance = self._instances.get(instance_id)
            if not instance:
                return None
            # Copie les données sous lock
            positions_snapshot = instance.get_positions_snapshot()

        return positions_snapshot
