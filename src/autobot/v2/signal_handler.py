"""
Signal Handler - Connecte les signaux des stratégies aux exécutions réelles

Ce module est le pont entre les stratégies (qui analysent et décident)
et l'exécution réelle des trades sur Kraken.
"""

import logging
from typing import Optional, Callable
from datetime import datetime

from .strategies import TradingSignal, SignalType
from .instance import TradingInstance

logger = logging.getLogger(__name__)


class SignalHandler:
    """
    Gestionnaire de signaux de trading.
    
    Responsabilités:
    1. Recevoir les signaux des stratégies (BUY, SELL)
    2. Valider les signaux (vérifier fonds, limites, etc.)
    3. Exécuter les ordres via l'instance
    4. Gérer les erreurs et les retries
    """
    
    def __init__(self, instance: TradingInstance):
        self.instance = instance
        self._last_signal_time: Optional[datetime] = None
        self._cooldown_seconds = 5  # Minimum 5s entre ordres
        
        # Callback pour recevoir les signaux
        self._setup_signal_callback()
        
        logger.info(f"📡 SignalHandler initialisé pour {instance.id}")
    
    def _setup_signal_callback(self):
        """Configure le callback pour recevoir les signaux de la stratégie"""
        if self.instance._strategy:
            self.instance._strategy.set_signal_callback(self._on_signal)
            
            # CORRECTION: Connecter les callbacks de l'instance à la stratégie
            self.instance._on_position_open = lambda inst, pos: self._on_position_opened(pos)
            self.instance._on_position_close = lambda inst, pos: self._on_position_closed(pos)
            
            logger.info(f"🔗 Callbacks configurés pour {self.instance.id}")
        else:
            logger.warning(f"⚠️ Pas de stratégie sur {self.instance.id}")
    
    def _on_position_opened(self, position):
        """Appelé quand une position est ouverte"""
        if self.instance._strategy:
            try:
                self.instance._strategy.on_position_opened(position)
            except Exception as e:
                logger.exception(f"❌ Erreur on_position_opened: {e}")
    
    def _on_position_closed(self, position):
        """Appelé quand une position est fermée"""
        if self.instance._strategy:
            try:
                profit = position.profit if hasattr(position, 'profit') else 0.0
                self.instance._strategy.on_position_closed(position, profit)
            except Exception as e:
                logger.exception(f"❌ Erreur on_position_closed: {e}")
    
    def _on_signal(self, signal: TradingSignal):
        """
        Appelé à chaque signal émis par la stratégie.
        C'est ici que la magie opère : signal → exécution réelle.
        """
        logger.info(f"📡 Signal reçu: {signal.type.value.upper()} {signal.symbol} @ {signal.price:.2f}")
        logger.info(f"   Raison: {signal.reason}")
        
        # Vérification cooldown (évite le spam d'ordres)
        if self._last_signal_time:
            elapsed = (datetime.now() - self._last_signal_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                logger.warning(f"⏱️ Signal ignoré (cooldown): {elapsed:.1f}s < {self._cooldown_seconds}s")
                return
        
        # Dispatch selon le type de signal
        try:
            if signal.type == SignalType.BUY:
                self._execute_buy(signal)
            elif signal.type == SignalType.SELL:
                self._execute_sell(signal)
            elif signal.type == SignalType.CLOSE:
                self._execute_close(signal)
            else:
                logger.debug(f"ℹ️ Signal {signal.type.value} ignoré (pas d'action)")
            
            self._last_signal_time = datetime.now()
            
        except Exception as e:
            logger.exception(f"❌ Erreur exécution signal: {e}")
    
    def _execute_buy(self, signal: TradingSignal):
        """
        Exécute un ordre d'achat.
        Valide puis appelle instance.open_position().
        """
        logger.info(f"🛒 Exécution ACHAT {signal.symbol}")
        
        # CORRECTION: Utilise get_available_capital() (thread-safe)
        # Capital disponible = total - alloué dans positions ouvertes
        available = self.instance.get_available_capital()
        
        if available < 10.0:  # Minimum 10€ pour un trade
            logger.error(f"❌ Capital disponible insuffisant: {available:.2f}€ < 10€ minimum")
            return
        
        # Détermine le volume à acheter
        if signal.volume > 0:
            # Volume spécifié par la stratégie
            volume = signal.volume
        else:
            # CORRECTION: 10% du capital disponible (pas total)
            volume = (available * 0.10) / signal.price
        
        # Arrondi à 6 décimales (précision BTC)
        volume = round(volume, 6)
        
        # Calcul le stop-loss et take-profit (pour log uniquement, pas encore utilisé)
        sl_price = signal.price * 0.95  # -5%
        tp_price = signal.price * 1.10  # +10%
        
        logger.info(f"   Volume: {volume} @ {signal.price:.2f}€")
        logger.info(f"   SL: {sl_price:.2f}€ (-5%) | TP: {tp_price:.2f}€ (+10%)")
        logger.info(f"   Capital dispo: {available:.2f}€")
        
        # CORRECTION: Appel avec bons arguments (price, volume) pas (entry_price, ...)
        position = self.instance.open_position(
            price=signal.price,
            volume=volume
        )
        
        if position:
            logger.info(f"✅ Ordre ACHAT exécuté avec succès (position {position.id})")
        else:
            logger.error(f"❌ Échec exécution ordre ACHAT")
    
    def _execute_sell(self, signal: TradingSignal):
        """
        Exécute un ordre de vente (fermeture position).
        """
        logger.info(f"💰 Exécution VENTE {signal.symbol}")
        
        # Si volume = -1 ou close_all flag → fermer toutes les positions
        close_all = signal.volume == -1 or signal.metadata.get('close_all', False)
        
        # CORRECTION: Utilise get_positions_snapshot() pour thread-safety
        positions_snapshot = self.instance.get_positions_snapshot()
        open_positions = [p for p in positions_snapshot if p.get('status') == 'open']
        
        if close_all:
            logger.info(f"   Mode: Fermeture TOUTES les positions ({len(open_positions)} ouvertes)")
            # Ferme toutes les positions ouvertes
            for pos in open_positions:
                pos_id = pos.get('id')
                if pos_id:
                    self.instance.close_position(pos_id, signal.price)
        else:
            # Ferme la dernière position ouverte
            if open_positions:
                pos_id = open_positions[-1].get('id')
                self.instance.close_position(pos_id, signal.price)
            else:
                logger.warning("⚠️ Pas de position à fermer")
    
    def _execute_close(self, signal: TradingSignal):
        """Alias pour SELL avec confirmation"""
        self._execute_sell(signal)
    
    def get_stats(self) -> dict:
        """Retourne les statistiques du handler"""
        return {
            'last_signal': self._last_signal_time.isoformat() if self._last_signal_time else None,
            'cooldown_seconds': self._cooldown_seconds,
            'instance_id': self.instance.id
        }
