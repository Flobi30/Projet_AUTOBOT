"""
Position Manager - Gestion des positions et cycle BUY→SELL
"""

import logging
from typing import Dict, List, Optional, Callable, cast
from dataclasses import dataclass
from enum import Enum

from .order_manager import OrderManager, Order, OrderSide
from .grid_calculator import GridCalculator

logger = logging.getLogger(__name__)

# Constantes de sécurité
MAX_POSITIONS = 10  # Nombre max de positions ouvertes simultanément
MAX_DRAWDOWN_PERCENT = 20.0  # Stop-loss global (% du capital)
KRAKEN_MAKER_FEE = 0.0016  # 0.16%
KRAKEN_TAKER_FEE = 0.0026  # 0.26%


class PositionStatus(Enum):
    """Statut d'une position"""
    OPEN = "open"           # Position ouverte, en attente
    PARTIAL = "partial"     # Partiellement remplie
    FILLED = "filled"       # Complètement remplie (SELL en attente)
    CLOSED = "closed"       # Position fermée (cycle terminé)


@dataclass
class Position:
    """Représente une position de trading"""
    buy_order_id: str
    buy_price: float
    volume: float
    sell_order_id: Optional[str] = None
    sell_price: Optional[float] = None
    status: PositionStatus = PositionStatus.OPEN
    profit: float = 0.0
    
    def calculate_profit(self) -> float:
        """
        Calcule le profit réel après frais.
        
        CORRECTION: Les frais sont sur le volume total échangé,
        pas sur le profit.
        """
        if self.sell_price is None:
            return 0.0
        
        # Volume total échangé (BUY + SELL)
        volume_buy = self.buy_price * self.volume
        volume_sell = self.sell_price * self.volume
        
        # Frais sur chaque transaction (maker/taker moyen ~0.21%)
        avg_fee_rate = (KRAKEN_MAKER_FEE + KRAKEN_TAKER_FEE) / 2
        fees_buy = volume_buy * avg_fee_rate
        fees_sell = volume_sell * avg_fee_rate
        total_fees = fees_buy + fees_sell
        
        # Profit brut
        gross_profit = (self.sell_price - self.buy_price) * self.volume
        
        # Profit net après frais
        net_profit = gross_profit - total_fees
        
        return net_profit
    
    def get_drawdown_percent(self, current_price: float) -> float:
        """
        Calcule le drawdown actuel de la position.
        
        Args:
            current_price: Prix actuel du marché
            
        Returns:
            Drawdown en pourcentage (négatif si perte)
        """
        if self.buy_price <= 0:
            return 0.0
        return ((current_price - self.buy_price) / self.buy_price) * 100


class PositionManager:
    """
    Gère le cycle complet des positions: BUY → SELL → Profit.
    
    Features:
    - Suivi des positions ouvertes
    - Détection des ordres BUY remplis
    - Placement automatique des ordres SELL
    - Calcul des profits (frais inclus)
    - Stop-loss global (max drawdown)
    - Nettoyage mémoire (positions fermées)
    """
    
    def __init__(
        self,
        order_manager: OrderManager,
        grid_calculator: GridCalculator,
        max_positions: int = MAX_POSITIONS,
        max_drawdown_percent: float = MAX_DRAWDOWN_PERCENT
    ):
        """
        Initialise le gestionnaire de positions.
        
        Args:
            order_manager: Gestionnaire d'ordres
            grid_calculator: Calculateur de grille
            max_positions: Nombre max de positions ouvertes
            max_drawdown_percent: Stop-loss global (%)
        """
        self.order_manager = order_manager
        self.grid_calculator = grid_calculator
        self.max_positions = max_positions
        self.max_drawdown_percent = max_drawdown_percent
        
        # Positions actives
        self._positions: Dict[str, Position] = {}  # buy_order_id -> Position
        self._positions_by_sell: Dict[str, str] = {}  # sell_order_id -> buy_order_id
        
        # Capital initial pour calcul du drawdown (à setter au démarrage)
        self._initial_capital: Optional[float] = None
        
        # Callbacks
        self._on_position_filled: Optional[Callable] = None
        self._on_profit_realized: Optional[Callable] = None
        self._on_stop_loss_triggered: Optional[Callable] = None
        
        logger.info(
            f"📈 PositionManager initialisé "
            f"(max_positions={max_positions}, max_drawdown={max_drawdown_percent}%)"
        )
    
    def set_initial_capital(self, capital: float):
        """Définit le capital initial pour le calcul du drawdown."""
        self._initial_capital = capital
        logger.info(f"💰 Capital initial défini: €{capital:,.2f}")
    
    def can_open_position(self) -> bool:
        """Vérifie si on peut ouvrir une nouvelle position (limite non atteinte)."""
        open_count = len(self.get_open_positions())
        return open_count < self.max_positions
    
    def open_position(self, buy_order: Order) -> Optional[Position]:
        """
        Ouvre une nouvelle position à partir d'un ordre BUY.
        
        Args:
            buy_order: Ordre d'achat créé
            
        Returns:
            Position créée, ou None si limite atteinte
        """
        if not buy_order.is_buy():
            raise ValueError("L'ordre doit être un ordre d'achat (BUY)")

        # Contrat: un ordre BUY tracké doit toujours avoir un identifiant non nul.
        if not buy_order.id:
            raise ValueError("buy_order.id manquant")

        buy_order_id = cast(str, buy_order.id)
        
        # Vérifie la limite de positions
        if not self.can_open_position():
            logger.warning(
                f"⚠️ Limite de positions atteinte ({self.max_positions}). "
                f"Impossible d'ouvrir une nouvelle position."
            )
            return None
        
        position = Position(
            buy_order_id=buy_order_id,
            buy_price=buy_order.price,
            volume=buy_order.volume,
            status=PositionStatus.OPEN
        )
        
        self._positions[buy_order_id] = position
        
        logger.info(
            f"📊 Position ouverte: BUY {buy_order.volume} @ €{buy_order.price:,.2f} "
            f"(ID: {buy_order_id}) - {len(self.get_open_positions())}/{self.max_positions}"
        )
        
        return position
    
    def check_and_fill_position(self, buy_order_id: str) -> Optional[Position]:
        """
        Vérifie si un ordre BUY est rempli et crée l'ordre SELL correspondant.
        
        Args:
            buy_order_id: ID non-null de l'ordre BUY
            
        Returns:
            Position mise à jour si remplie, None sinon
        """
        if buy_order_id not in self._positions:
            logger.warning(f"⚠️ Position {buy_order_id} non trouvée")
            return None
        
        position = self._positions[buy_order_id]
        
        # Vérifie si déjà traité
        if position.status in (PositionStatus.FILLED, PositionStatus.CLOSED):
            return position
        
        # Récupère le statut actuel de l'ordre BUY (force refresh)
        buy_order = self.order_manager.get_order_status(buy_order_id, force_refresh=True)
        
        if not buy_order:
            logger.warning(f"⚠️ Ordre BUY {buy_order_id} introuvable")
            return None
        
        # Vérifie si l'ordre est rempli
        if not buy_order.is_filled():
            if buy_order.filled_volume > 0 and buy_order.filled_volume < buy_order.volume:
                position.status = PositionStatus.PARTIAL
            return None
        
        # 🎉 Ordre BUY rempli ! On crée l'ordre SELL
        logger.info(
            f"✅ Ordre BUY rempli: {buy_order.volume} @ €{buy_order.price:,.2f}"
        )
        
        # Calcule le prix de vente (niveau supérieur de la grille)
        sell_price = self._calculate_sell_price(buy_order.price)
        
        try:
            # Place l'ordre SELL
            sell_order = self.order_manager.place_sell_order(
                symbol=buy_order.symbol or "XXBTZEUR",
                price=sell_price,
                volume=buy_order.volume
            )
            
            if not sell_order.id:
                raise ValueError("sell_order.id manquant")
            sell_order_id = cast(str, sell_order.id)

            # Met à jour la position
            position.sell_order_id = sell_order_id
            position.sell_price = sell_price
            position.status = PositionStatus.FILLED
            position.profit = position.calculate_profit()
            
            # Indexe par sell_order_id pour suivi futur
            self._positions_by_sell[sell_order_id] = buy_order_id
            
            logger.info(
                f"📈 Ordre SELL placé: {buy_order.volume} @ €{sell_price:,.2f} "
                f"(Profit estimé: €{position.profit:.2f})"
            )
            
            # Callback
            if self._on_position_filled:
                self._on_position_filled(position)
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Échec placement ordre SELL: {e}")
            return None
    
    def _calculate_sell_price(self, buy_price: float) -> float:
        """
        Calcule le prix de vente pour une position.
        
        Par défaut: niveau supérieur le plus proche dans la grille.
        
        Args:
            buy_price: Prix d'achat
            
        Returns:
            Prix de vente recommandé
        """
        # Trouve le niveau supérieur le plus proche
        sell_levels = self.grid_calculator.get_sell_levels()
        
        if not sell_levels:
            # Fallback: +0.8% si pas de grille calculée
            return buy_price * 1.008
        
        # Prend le premier niveau supérieur au prix d'achat
        for level in sorted(sell_levels):
            if level > buy_price:
                return level
        
        # Fallback: dernier niveau + marge
        return sell_levels[-1] * 1.001
    
    def check_position_closed(self, sell_order_id: str) -> Optional[Position]:
        """
        Vérifie si un ordre SELL est rempli (position complètement fermée).
        
        Args:
            sell_order_id: ID de l'ordre SELL
            
        Returns:
            Position fermée avec profit réalisé, ou None
        """
        if sell_order_id not in self._positions_by_sell:
            return None
        
        buy_order_id = self._positions_by_sell[sell_order_id]
        position = self._positions.get(buy_order_id)
        
        if not position:
            return None
        
        # Vérifie le statut de l'ordre SELL (force refresh)
        sell_order = self.order_manager.get_order_status(sell_order_id, force_refresh=True)
        
        if not sell_order:
            return None
        
        if sell_order.is_filled():
            # 🎉 Position complètement fermée !
            position.status = PositionStatus.CLOSED
            position.profit = position.calculate_profit()
            
            logger.info(
                f"💰 POSITION FERMÉE ! Profit réalisé: €{position.profit:.2f} "
                f"(BUY €{position.buy_price:,.2f} → SELL €{position.sell_price:,.2f})"
            )
            
            # Callback
            if self._on_profit_realized:
                self._on_profit_realized(position)
            
            return position
        
        return None
    
    def check_stop_loss(self, current_price: float) -> bool:
        """
        Vérifie le stop-loss global (max drawdown).
        
        Args:
            current_price: Prix actuel du marché
            
        Returns:
            True si stop-loss déclenché, False sinon
        """
        if self._initial_capital is None or self._initial_capital <= 0:
            return False
        
        # Calcule la valeur actuelle des positions ouvertes
        open_positions = self.get_open_positions()
        if not open_positions:
            return False
        
        total_value = sum(
            pos.volume * current_price for pos in open_positions
        )
        
        # Calcule le drawdown global
        if total_value <= 0:
            return False
        
        # Valeur investie (prix d'achat)
        invested_value = sum(
            pos.volume * pos.buy_price for pos in open_positions
        )
        
        drawdown_percent = ((total_value - invested_value) / invested_value) * 100
        
        if drawdown_percent <= -self.max_drawdown_percent:
            logger.error(
                f"🚨 STOP-LOSS DÉCLENCHÉ ! Drawdown: {drawdown_percent:.1f}% "
                f"(limite: -{self.max_drawdown_percent}%)"
            )
            
            # Ferme toutes les positions
            self.close_all_positions()
            
            # Callback
            if self._on_stop_loss_triggered:
                self._on_stop_loss_triggered(drawdown_percent)
            
            return True
        
        return False
    
    def scan_all_positions(self) -> Dict[str, Position]:
        """
        Scanne toutes les positions et met à jour leur statut.
        
        Returns:
            Dictionnaire des positions mises à jour
        """
        updated = {}
        
        for buy_order_id in list(self._positions.keys()):
            position = self._positions[buy_order_id]
            
            # Vérifie les positions ouvertes
            if position.status == PositionStatus.OPEN:
                updated_pos = self.check_and_fill_position(buy_order_id)
                if updated_pos:
                    updated[buy_order_id] = updated_pos
            
            # Vérifie les positions remplies (attente SELL)
            elif position.status == PositionStatus.FILLED and position.sell_order_id:
                closed_pos = self.check_position_closed(position.sell_order_id)
                if closed_pos:
                    updated[buy_order_id] = closed_pos
        
        return updated
    
    def get_open_positions(self) -> List[Position]:
        """
        Retourne toutes les positions ouvertes.
        
        Returns:
            Liste des positions ouvertes
        """
        return [
            pos for pos in self._positions.values()
            if pos.status in (PositionStatus.OPEN, PositionStatus.PARTIAL)
        ]
    
    def get_filled_positions(self) -> List[Position]:
        """
        Retourne les positions avec ordre SELL en attente.
        
        Returns:
            Liste des positions remplies
        """
        return [
            pos for pos in self._positions.values()
            if pos.status == PositionStatus.FILLED
        ]
    
    def get_closed_positions(self) -> List[Position]:
        """
        Retourne les positions fermées (cycle complet).
        
        Returns:
            Liste des positions fermées
        """
        return [
            pos for pos in self._positions.values()
            if pos.status == PositionStatus.CLOSED
        ]
    
    def get_total_profit(self) -> float:
        """
        Calcule le profit total des positions fermées.
        
        Returns:
            Profit total en EUR
        """
        return sum(pos.profit for pos in self.get_closed_positions())
    
    def cleanup_closed_positions(self, max_closed: int = 100) -> int:
        """
        Nettoie les positions fermées du cache pour éviter la fuite mémoire.
        Garde uniquement les N dernières positions fermées.
        
        Args:
            max_closed: Nombre max de positions fermées à garder
            
        Returns:
            Nombre de positions nettoyées
        """
        closed_positions = self.get_closed_positions()
        
        if len(closed_positions) <= max_closed:
            return 0
        
        # Trie par ordre de création (approximatif via l'ID)
        to_remove = closed_positions[:-max_closed]
        
        count = 0
        for pos in to_remove:
            buy_id = pos.buy_order_id
            sell_id = pos.sell_order_id
            
            # Supprime de _positions
            if buy_id in self._positions:
                del self._positions[buy_id]
                count += 1
            
            # Supprime de _positions_by_sell
            if sell_id and sell_id in self._positions_by_sell:
                del self._positions_by_sell[sell_id]
        
        if count > 0:
            logger.info(f"🧹 {count} positions fermées archivées (garde {max_closed})")
        
        return count
    
    def set_callbacks(
        self,
        on_position_filled: Optional[Callable] = None,
        on_profit_realized: Optional[Callable] = None,
        on_stop_loss_triggered: Optional[Callable] = None
    ):
        """
        Définit les callbacks pour les événements.
        
        Args:
            on_position_filled: Appelé quand un BUY est rempli et SELL placé
            on_profit_realized: Appelé quand une position est complètement fermée
            on_stop_loss_triggered: Appelé quand le stop-loss est déclenché
        """
        self._on_position_filled = on_position_filled
        self._on_profit_realized = on_profit_realized
        self._on_stop_loss_triggered = on_stop_loss_triggered
    
    def close_all_positions(self) -> int:
        """
        Ferme toutes les positions (annule les ordres).
        
        Returns:
            Nombre de positions fermées
        """
        count = 0
        
        for position in self.get_open_positions():
            try:
                self.order_manager.cancel_order(position.buy_order_id)
                position.status = PositionStatus.CLOSED
                count += 1
            except Exception as e:
                logger.error(f"❌ Erreur fermeture position {position.buy_order_id}: {e}")
        
        for position in self.get_filled_positions():
            if position.sell_order_id:
                try:
                    self.order_manager.cancel_order(position.sell_order_id)
                    position.status = PositionStatus.CLOSED
                    count += 1
                except Exception as e:
                    logger.error(f"❌ Erreur fermeture SELL {position.sell_order_id}: {e}")
        
        logger.info(f"🗑️ {count} positions fermées")
        return count
