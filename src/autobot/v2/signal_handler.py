"""
Signal Handler - Connecte les signaux des stratégies aux exécutions réelles sur Kraken

CORRECTION CRITIQUE : Utilise OrderExecutor pour passer de VRAIS ordres sur Kraken,
pas seulement mettre à jour l'état local.
"""

import logging
from typing import Optional, Callable
from datetime import datetime

from .strategies import TradingSignal, SignalType
from .instance import TradingInstance
from .order_executor import OrderExecutor, OrderSide
from .validator import ValidatorEngine, ValidationResult, ValidationStatus, create_default_validator_engine
from .stop_loss_manager import get_stop_loss_manager

logger = logging.getLogger(__name__)


class SignalHandler:
    """
    Gestionnaire de signaux de trading.
    
    Responsabilités:
    1. Recevoir les signaux des stratégies (BUY, SELL)
    2. Valider les signaux via ValidatorEngine (voyants au vert)
    3. Exécuter les ordres RÉELS via OrderExecutor sur Kraken
    4. Mettre à jour l'état local avec les prix d'exécution réels
    5. Poser stop-loss sur Kraken (pas logiciel)
    """
    
    def __init__(self, instance: TradingInstance, order_executor: Optional[OrderExecutor] = None):
        self.instance = instance
        self.order_executor = order_executor
        # CORRECTION E5: Utilise create_default_validator_engine() au lieu de ValidatorEngine() vide
        self.validator = create_default_validator_engine()
        self._last_signal_time: Optional[datetime] = None
        self._cooldown_seconds = 5  # Minimum 5s entre ordres
        
        # Callback pour recevoir les signaux
        self._setup_signal_callback()
        
        logger.info(f"📡 SignalHandler initialisé pour {instance.id}")
    
    def _setup_signal_callback(self):
        """Configure le callback pour recevoir les signaux de la stratégie"""
        if self.instance._strategy:
            self.instance._strategy.set_signal_callback(self._on_signal)
            logger.info(f"🔗 Callback signal configuré pour {self.instance.id}")
        else:
            logger.warning(f"⚠️ Pas de stratégie sur {self.instance.id}")
    
    def _on_signal(self, signal: TradingSignal):
        """
        Appelé à chaque signal émis par la stratégie.
        """
        logger.info(f"📡 Signal reçu: {signal.type.value.upper()} {signal.symbol} @ {signal.price:.2f}")
        logger.info(f"   Raison: {signal.reason}")
        
        # Vérification cooldown
        if self._last_signal_time:
            elapsed = (datetime.now() - self._last_signal_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                logger.warning(f"⏱️ Signal ignoré (cooldown): {elapsed:.1f}s < {self._cooldown_seconds}s")
                return
        
        # Dispatch selon le type
        try:
            if signal.type == SignalType.BUY:
                self._execute_buy(signal)
            elif signal.type == SignalType.SELL:
                self._execute_sell(signal)
            elif signal.type == SignalType.CLOSE:
                self._execute_sell(signal)
            
            self._last_signal_time = datetime.now()
            
        except Exception as e:
            logger.exception(f"❌ Erreur exécution signal: {e}")
    
    def _execute_buy(self, signal: TradingSignal):
        """
        Exécute un ordre d'achat RÉEL sur Kraken.
        
        CORRECTION CRITIQUE :
        1. Valide via ValidatorEngine
        2. Passe ordre MARKET BUY réel via OrderExecutor
        3. Attend confirmation et prix d'exécution réel
        4. Pose stop-loss sur Kraken (pas logiciel)
        5. Met à jour état local avec données réelles
        """
        logger.info(f"🛒 Exécution ACHAT {signal.symbol}")
        
        # CORRECTION: Validation via ValidatorEngine (était contournée !)
        available = self.instance.get_available_capital()
        context = {
            'available_capital': available,
            'signal_price': signal.price,
            'instance_status': self.instance.status.value,
            'open_positions_count': len([p for p in self.instance.get_positions_snapshot() if p.get('status') == 'open']),
            'max_positions': getattr(self.instance.config, 'max_positions', 10)
        }
        
        validation = self.validator.validate('open_position', context)
        if validation.status == ValidationStatus.RED:
            logger.error(f"❌ Signal BUY rejeté par validateur: {validation.message}")
            return
        elif validation.status == ValidationStatus.YELLOW:
            logger.warning(f"⚠️ Signal BUY avec avertissement: {validation.message}")
        
        # Vérification OrderExecutor
        if self.order_executor is None:
            logger.error("❌ OrderExecutor non configuré - impossible de passer ordre réel")
            return
        
        # Calcul volume
        if signal.volume > 0:
            volume = signal.volume
        else:
            volume = (available * 0.10) / signal.price
        
        volume = round(volume, 6)
        
        if volume <= 0:
            logger.error(f"❌ Volume calculé invalide: {volume}")
            return
        
        # CORRECTION: Exécution RÉELLE sur Kraken
        symbol = self._convert_symbol(signal.symbol)  # ex: BTC/EUR → XXBTZEUR
        
        logger.info(f"   Envoi ordre MARKET BUY {volume:.6f} {symbol}...")
        
        result = self.order_executor.execute_market_order(
            symbol=symbol,
            side=OrderSide.BUY,
            volume=volume
        )
        
        if not result.success:
            logger.error(f"❌ Échec ordre Kraken: {result.error}")
            return
        
        # Récupération prix d'exécution RÉEL
        executed_price = result.executed_price or signal.price
        executed_volume = result.executed_volume or volume
        fees = result.fees or 0.0
        
        logger.info(f"✅ Ordre exécuté sur Kraken: {executed_volume:.6f} @ {executed_price:.2f}€ (frais: {fees:.4f}€)")
        
        # CORRECTION: Poser stop-loss RÉEL sur Kraken AVANT création position
        stop_price = executed_price * 0.95  # -5%
        sl_result = self.order_executor.execute_stop_loss_order(
            symbol=symbol,
            side=OrderSide.SELL,
            volume=executed_volume,
            stop_price=stop_price
        )
        
        stop_loss_txid = None
        if sl_result.success:
            stop_loss_txid = sl_result.txid
            logger.info(f"🛡️ Stop-loss posé sur Kraken @ {stop_price:.2f}€ (txid: {stop_loss_txid[:8]}...)")
        else:
            logger.error(f"❌ Échec stop-loss Kraken: {sl_result.error}")
            # Continue quand même - la position sera sans protection

        # CORRECTION: Créer position avec prix d'exécution réel ET txids
        position = self.instance.open_position(
            price=executed_price,
            volume=executed_volume,
            stop_loss=stop_price,
            stop_loss_txid=stop_loss_txid,
            buy_txid=result.txid  # CORRECTION Phase 3: TXID de l'achat
        )

        # CORRECTION CRITIQUE: Enregistre le stop-loss dans StopLossManager pour surveillance
        if position and stop_loss_txid:
            sl_manager = get_stop_loss_manager()
            sl_manager.register_stop_loss(stop_loss_txid, position.id)
            logger.info(f"🛡️ Stop-loss enregistré pour surveillance: {position.id}")

        if position:
            logger.info(f"✅ Position créée: {position.id}")
        else:
            logger.error(f"❌ Échec création position locale")
    
    def _execute_sell(self, signal: TradingSignal):
        """
        Exécute un ordre de vente RÉEL sur Kraken.
        
        CORRECTION CRITIQUE :
        1. Identifie la position à fermer (métadonnées du signal)
        2. Passe ordre MARKET SELL réel via OrderExecutor
        3. Attend confirmation et prix d'exécution réel
        4. Met à jour position avec P&L réel
        """
        logger.info(f"💰 Exécution VENTE {signal.symbol}")
        
        # Vérification OrderExecutor
        if self.order_executor is None:
            logger.error("❌ OrderExecutor non configuré - impossible de passer ordre réel")
            return
        
        # Récupère position à fermer (depuis métadonnées si spécifié)
        level_index = signal.metadata.get('level_index')
        close_all = signal.volume == -1 or signal.metadata.get('close_all', False)
        
        # CORRECTION: Récupère positions ouvertes
        positions_snapshot = self.instance.get_positions_snapshot()
        open_positions = [p for p in positions_snapshot if p.get('status') == 'open']
        
        if not open_positions:
            logger.warning("⚠️ Pas de position ouverte à fermer")
            return
        
        # Détermine quelles positions fermer
        positions_to_close = []
        if close_all:
            positions_to_close = open_positions
            logger.info(f"   Fermeture de {len(positions_to_close)} position(s)")
        elif level_index is not None:
            # Grid: trouve position correspondant au niveau
            # Note: nécessite que grid.py passe level_index dans metadata
            positions_to_close = open_positions  # Fallback: ferme toutes
        else:
            # Fallback: ferme la dernière
            positions_to_close = [open_positions[-1]]
        
        symbol = self._convert_symbol(signal.symbol)
        
        for pos_info in positions_to_close:
            pos_id = pos_info.get('id')
            volume = pos_info.get('volume', 0)
            
            if not pos_id or volume <= 0:
                continue
            
            # CORRECTION: Annule stop-loss existant si présent
            stop_loss_txid = pos_info.get('stop_loss_txid')
            if stop_loss_txid:
                self.order_executor.cancel_order(stop_loss_txid)
                # CORRECTION: Retire aussi du StopLossManager
                sl_manager = get_stop_loss_manager()
                sl_manager.unregister_stop_loss(stop_loss_txid)
            
            # CORRECTION: Exécution RÉELLE sur Kraken
            logger.info(f"   Envoi ordre MARKET SELL {volume:.6f} {symbol}...")
            
            result = self.order_executor.execute_market_order(
                symbol=symbol,
                side=OrderSide.SELL,
                volume=volume
            )
            
            if result.success:
                executed_price = result.executed_price or signal.price
                logger.info(f"✅ Vente exécutée: {volume:.6f} @ {executed_price:.2f}€")

                # Met à jour position avec prix réel et txid
                self.instance.close_position(pos_id, executed_price, sell_txid=result.txid)  # Phase 3
            else:
                logger.error(f"❌ Échec vente: {result.error}")
    
    def _convert_symbol(self, symbol: str) -> str:
        """
        Convertit symbole interne (BTC/EUR) en format Kraken (XXBTZEUR).
        """
        mapping = {
            'BTC/EUR': 'XXBTZEUR',
            'ETH/EUR': 'XETHZEUR',
            'BTC/USD': 'XXBTZUSD',
            'ETH/USD': 'XETHZUSD',
        }
        return mapping.get(symbol, symbol.replace('/', ''))
    
    def get_stats(self) -> dict:
        """Retourne les statistiques du handler"""
        return {
            'last_signal': self._last_signal_time.isoformat() if self._last_signal_time else None,
            'cooldown_seconds': self._cooldown_seconds,
            'instance_id': self.instance.id,
            'has_order_executor': self.order_executor is not None
        }
