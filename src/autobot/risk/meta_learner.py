"""
AUTOBOT Meta-Learner Orchestrator

ML-based strategy orchestration system that:
- Analyzes performance of all strategies
- Chooses which strategies to activate
- Dynamically adjusts allocations
- Provides fallback when ML is unavailable
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable
import json
import os
import random

logger = logging.getLogger(__name__)


class StrategyStatus(Enum):
    """Strategy activation status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    DISABLED = "disabled"


class RiskProfile(Enum):
    """Risk profile for allocation"""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class StrategyPerformance:
    """Performance metrics for a strategy"""
    strategy_id: str
    strategy_name: str
    strategy_type: str  # scalping, trend, arbitrage, mean_reversion, news_based
    
    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade_duration_minutes: float = 0.0
    
    # Recent performance (last 30 days)
    recent_trades: int = 0
    recent_pnl: float = 0.0
    recent_win_rate: float = 0.0
    
    # Risk metrics
    volatility: float = 0.0
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0
    
    # Status
    status: StrategyStatus = StrategyStatus.INACTIVE
    allocation_pct: float = 0.0
    last_trade_time: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": self.total_pnl,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_trade_duration_minutes": self.avg_trade_duration_minutes,
            "recent_trades": self.recent_trades,
            "recent_pnl": self.recent_pnl,
            "recent_win_rate": self.recent_win_rate,
            "volatility": self.volatility,
            "max_consecutive_losses": self.max_consecutive_losses,
            "current_consecutive_losses": self.current_consecutive_losses,
            "status": self.status.value,
            "allocation_pct": self.allocation_pct,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class AllocationDecision:
    """Allocation decision from Meta-Learner"""
    timestamp: datetime
    risk_profile: RiskProfile
    allocations: Dict[str, float]  # strategy_id -> allocation_pct
    reasoning: str
    confidence: float  # 0-1
    is_fallback: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "risk_profile": self.risk_profile.value,
            "allocations": self.allocations,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "is_fallback": self.is_fallback,
        }


class MetaLearner:
    """
    Meta-Learner Orchestrator for AUTOBOT.
    
    Analyzes strategy performance and dynamically allocates capital
    across strategies based on their historical and recent performance.
    
    Features:
    - Performance-based strategy ranking
    - Dynamic allocation adjustment
    - Risk-adjusted weighting
    - Fallback to equal weighting when ML unavailable
    - Strategy activation/deactivation based on performance
    """
    
    # Default allocation limits
    DEFAULT_MAX_ALLOCATION_PER_STRATEGY = 0.25  # 25% max per strategy
    DEFAULT_MIN_ALLOCATION_PER_STRATEGY = 0.05  # 5% min per strategy
    DEFAULT_MAX_STRATEGIES = 5  # Max active strategies
    
    # Performance thresholds
    MIN_TRADES_FOR_EVALUATION = 10
    MIN_WIN_RATE_THRESHOLD = 0.4  # 40% minimum win rate
    MAX_CONSECUTIVE_LOSSES_THRESHOLD = 5
    MIN_SHARPE_RATIO = 0.5
    
    def __init__(
        self,
        data_dir: str = "/app/data",
        risk_profile: RiskProfile = RiskProfile.MODERATE,
        max_allocation_per_strategy: float = 0.25,
        min_allocation_per_strategy: float = 0.05,
        max_active_strategies: int = 5,
        ml_model_path: Optional[str] = None,
    ):
        self.data_dir = data_dir
        self.risk_profile = risk_profile
        self.max_allocation = max_allocation_per_strategy
        self.min_allocation = min_allocation_per_strategy
        self.max_active_strategies = max_active_strategies
        self.ml_model_path = ml_model_path
        
        # Strategy registry
        self.strategies: Dict[str, StrategyPerformance] = {}
        
        # Allocation history
        self.allocation_history: List[AllocationDecision] = []
        
        # ML model (optional)
        self.ml_model = None
        self.ml_available = False
        
        # Try to load ML model
        self._load_ml_model()
        
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
        
        logger.info(f"Meta-Learner initialized with {risk_profile.value} risk profile")
    
    # =========================================================================
    # Strategy Registration
    # =========================================================================
    
    def register_strategy(
        self,
        strategy_id: str,
        strategy_name: str,
        strategy_type: str,
    ) -> StrategyPerformance:
        """Register a new strategy with the Meta-Learner"""
        if strategy_id in self.strategies:
            logger.warning(f"Strategy {strategy_id} already registered, returning existing")
            return self.strategies[strategy_id]
        
        strategy = StrategyPerformance(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            last_updated=datetime.utcnow(),
        )
        
        self.strategies[strategy_id] = strategy
        logger.info(f"Registered strategy: {strategy_name} ({strategy_type})")
        
        return strategy
    
    def unregister_strategy(self, strategy_id: str) -> bool:
        """Unregister a strategy"""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            logger.info(f"Unregistered strategy: {strategy_id}")
            return True
        return False
    
    # =========================================================================
    # Performance Tracking
    # =========================================================================
    
    def record_trade(
        self,
        strategy_id: str,
        pnl: float,
        trade_duration_minutes: float = 0.0,
    ):
        """Record a trade result for a strategy"""
        if strategy_id not in self.strategies:
            logger.warning(f"Strategy {strategy_id} not registered")
            return
        
        strategy = self.strategies[strategy_id]
        
        # Update trade counts
        strategy.total_trades += 1
        strategy.recent_trades += 1
        
        if pnl > 0:
            strategy.winning_trades += 1
            strategy.current_consecutive_losses = 0
        else:
            strategy.losing_trades += 1
            strategy.current_consecutive_losses += 1
            strategy.max_consecutive_losses = max(
                strategy.max_consecutive_losses,
                strategy.current_consecutive_losses
            )
        
        # Update P&L
        strategy.total_pnl += pnl
        strategy.recent_pnl += pnl
        
        # Update win rate
        strategy.win_rate = strategy.winning_trades / strategy.total_trades if strategy.total_trades > 0 else 0
        strategy.recent_win_rate = (
            (strategy.recent_trades - strategy.current_consecutive_losses) / strategy.recent_trades
            if strategy.recent_trades > 0 else 0
        )
        
        # Update trade duration
        if trade_duration_minutes > 0:
            # Running average
            strategy.avg_trade_duration_minutes = (
                (strategy.avg_trade_duration_minutes * (strategy.total_trades - 1) + trade_duration_minutes)
                / strategy.total_trades
            )
        
        # Update timestamps
        strategy.last_trade_time = datetime.utcnow()
        strategy.last_updated = datetime.utcnow()
        
        # Check if strategy should be paused
        self._check_strategy_health(strategy_id)
        
        logger.debug(f"Recorded trade for {strategy_id}: P&L={pnl}, Win Rate={strategy.win_rate:.2%}")
    
    def update_strategy_metrics(
        self,
        strategy_id: str,
        sharpe_ratio: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        profit_factor: Optional[float] = None,
        volatility: Optional[float] = None,
    ):
        """Update additional metrics for a strategy"""
        if strategy_id not in self.strategies:
            logger.warning(f"Strategy {strategy_id} not registered")
            return
        
        strategy = self.strategies[strategy_id]
        
        if sharpe_ratio is not None:
            strategy.sharpe_ratio = sharpe_ratio
        if max_drawdown_pct is not None:
            strategy.max_drawdown_pct = max_drawdown_pct
        if profit_factor is not None:
            strategy.profit_factor = profit_factor
        if volatility is not None:
            strategy.volatility = volatility
        
        strategy.last_updated = datetime.utcnow()
    
    def reset_recent_metrics(self):
        """Reset recent metrics (call at start of new period)"""
        for strategy in self.strategies.values():
            strategy.recent_trades = 0
            strategy.recent_pnl = 0.0
            strategy.recent_win_rate = 0.0
        
        logger.info("Reset recent metrics for all strategies")
    
    # =========================================================================
    # Allocation Decision
    # =========================================================================
    
    def calculate_allocations(self) -> AllocationDecision:
        """
        Calculate optimal allocations across strategies.
        
        Uses ML model if available, otherwise falls back to
        performance-based heuristics.
        """
        if self.ml_available and self.ml_model is not None:
            try:
                return self._ml_based_allocation()
            except Exception as e:
                logger.error(f"ML allocation failed, using fallback: {e}")
        
        return self._fallback_allocation()
    
    def _ml_based_allocation(self) -> AllocationDecision:
        """Calculate allocations using ML model"""
        # Prepare features for ML model
        features = self._prepare_ml_features()
        
        # Get predictions from model
        # This is a placeholder - actual implementation depends on model type
        predictions = self.ml_model.predict(features)
        
        # Convert predictions to allocations
        allocations = self._predictions_to_allocations(predictions)
        
        return AllocationDecision(
            timestamp=datetime.utcnow(),
            risk_profile=self.risk_profile,
            allocations=allocations,
            reasoning="ML model prediction based on historical performance patterns",
            confidence=0.8,
            is_fallback=False,
        )
    
    def _fallback_allocation(self) -> AllocationDecision:
        """
        Fallback allocation when ML is unavailable.
        
        Uses performance-based ranking with risk-adjusted weighting.
        """
        # Get eligible strategies
        eligible = self._get_eligible_strategies()
        
        if not eligible:
            logger.warning("No eligible strategies for allocation")
            return AllocationDecision(
                timestamp=datetime.utcnow(),
                risk_profile=self.risk_profile,
                allocations={},
                reasoning="No eligible strategies available",
                confidence=0.0,
                is_fallback=True,
            )
        
        # Score strategies
        scores = {}
        for strategy_id in eligible:
            scores[strategy_id] = self._calculate_strategy_score(strategy_id)
        
        # Sort by score
        sorted_strategies = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Select top strategies
        selected = sorted_strategies[:self.max_active_strategies]
        
        # Calculate allocations based on risk profile
        allocations = self._calculate_weighted_allocations(selected)
        
        # Apply allocation limits
        allocations = self._apply_allocation_limits(allocations)
        
        # Generate reasoning
        reasoning = self._generate_allocation_reasoning(selected, allocations)
        
        decision = AllocationDecision(
            timestamp=datetime.utcnow(),
            risk_profile=self.risk_profile,
            allocations=allocations,
            reasoning=reasoning,
            confidence=0.6,  # Lower confidence for fallback
            is_fallback=True,
        )
        
        # Store in history
        self.allocation_history.append(decision)
        if len(self.allocation_history) > 100:
            self.allocation_history = self.allocation_history[-100:]
        
        return decision
    
    def _get_eligible_strategies(self) -> List[str]:
        """Get strategies eligible for allocation"""
        eligible = []
        
        for strategy_id, strategy in self.strategies.items():
            # Skip disabled strategies
            if strategy.status == StrategyStatus.DISABLED:
                continue
            
            # Need minimum trades for evaluation
            if strategy.total_trades < self.MIN_TRADES_FOR_EVALUATION:
                continue
            
            # Check win rate threshold
            if strategy.win_rate < self.MIN_WIN_RATE_THRESHOLD:
                continue
            
            # Check consecutive losses
            if strategy.current_consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES_THRESHOLD:
                continue
            
            eligible.append(strategy_id)
        
        return eligible
    
    def _calculate_strategy_score(self, strategy_id: str) -> float:
        """Calculate a composite score for a strategy"""
        strategy = self.strategies[strategy_id]
        
        # Base score from win rate (0-40 points)
        win_rate_score = strategy.win_rate * 40
        
        # Sharpe ratio score (0-30 points)
        sharpe_score = min(30, max(0, strategy.sharpe_ratio * 10))
        
        # Profit factor score (0-20 points)
        pf_score = min(20, max(0, (strategy.profit_factor - 1) * 10))
        
        # Recent performance bonus/penalty (-10 to +10 points)
        if strategy.recent_trades > 0:
            recent_score = (strategy.recent_win_rate - 0.5) * 20
        else:
            recent_score = 0
        
        # Drawdown penalty (0 to -20 points)
        drawdown_penalty = -min(20, strategy.max_drawdown_pct)
        
        # Consecutive losses penalty
        loss_penalty = -strategy.current_consecutive_losses * 2
        
        total_score = (
            win_rate_score +
            sharpe_score +
            pf_score +
            recent_score +
            drawdown_penalty +
            loss_penalty
        )
        
        return max(0, total_score)
    
    def _calculate_weighted_allocations(
        self,
        scored_strategies: List[Tuple[str, float]],
    ) -> Dict[str, float]:
        """Calculate weighted allocations based on scores"""
        if not scored_strategies:
            return {}
        
        total_score = sum(score for _, score in scored_strategies)
        
        if total_score == 0:
            # Equal weighting if all scores are 0
            equal_weight = 1.0 / len(scored_strategies)
            return {strategy_id: equal_weight for strategy_id, _ in scored_strategies}
        
        # Score-based weighting
        allocations = {}
        for strategy_id, score in scored_strategies:
            allocations[strategy_id] = score / total_score
        
        # Adjust based on risk profile
        if self.risk_profile == RiskProfile.CONSERVATIVE:
            # More equal distribution
            allocations = self._smooth_allocations(allocations, factor=0.5)
        elif self.risk_profile == RiskProfile.AGGRESSIVE:
            # More concentrated in top performers
            allocations = self._concentrate_allocations(allocations, factor=1.5)
        
        return allocations
    
    def _smooth_allocations(
        self,
        allocations: Dict[str, float],
        factor: float = 0.5,
    ) -> Dict[str, float]:
        """Smooth allocations towards equal weighting"""
        if not allocations:
            return allocations
        
        equal_weight = 1.0 / len(allocations)
        
        smoothed = {}
        for strategy_id, allocation in allocations.items():
            smoothed[strategy_id] = allocation * (1 - factor) + equal_weight * factor
        
        return smoothed
    
    def _concentrate_allocations(
        self,
        allocations: Dict[str, float],
        factor: float = 1.5,
    ) -> Dict[str, float]:
        """Concentrate allocations in top performers"""
        if not allocations:
            return allocations
        
        # Raise allocations to power to concentrate
        concentrated = {}
        for strategy_id, allocation in allocations.items():
            concentrated[strategy_id] = allocation ** factor
        
        # Normalize
        total = sum(concentrated.values())
        if total > 0:
            concentrated = {k: v / total for k, v in concentrated.items()}
        
        return concentrated
    
    def _apply_allocation_limits(
        self,
        allocations: Dict[str, float],
    ) -> Dict[str, float]:
        """Apply min/max allocation limits"""
        if not allocations:
            return allocations
        
        # Apply limits
        limited = {}
        for strategy_id, allocation in allocations.items():
            limited[strategy_id] = max(
                self.min_allocation,
                min(self.max_allocation, allocation)
            )
        
        # Normalize to sum to 1.0
        total = sum(limited.values())
        if total > 0:
            limited = {k: v / total for k, v in limited.items()}
        
        return limited
    
    def _generate_allocation_reasoning(
        self,
        selected: List[Tuple[str, float]],
        allocations: Dict[str, float],
    ) -> str:
        """Generate human-readable reasoning for allocation decision"""
        if not selected:
            return "No strategies selected due to insufficient performance data or poor metrics."
        
        parts = [f"Selected {len(selected)} strategies based on performance ranking."]
        
        for strategy_id, score in selected[:3]:  # Top 3
            strategy = self.strategies[strategy_id]
            alloc = allocations.get(strategy_id, 0) * 100
            parts.append(
                f"{strategy.strategy_name}: {alloc:.1f}% allocation "
                f"(score: {score:.1f}, win rate: {strategy.win_rate:.1%})"
            )
        
        parts.append(f"Risk profile: {self.risk_profile.value}")
        
        return " | ".join(parts)
    
    # =========================================================================
    # Strategy Health Management
    # =========================================================================
    
    def _check_strategy_health(self, strategy_id: str):
        """Check strategy health and update status"""
        strategy = self.strategies[strategy_id]
        
        # Check consecutive losses
        if strategy.current_consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES_THRESHOLD:
            if strategy.status == StrategyStatus.ACTIVE:
                strategy.status = StrategyStatus.PAUSED
                logger.warning(
                    f"Strategy {strategy_id} paused due to {strategy.current_consecutive_losses} consecutive losses"
                )
        
        # Check win rate degradation
        if strategy.total_trades >= self.MIN_TRADES_FOR_EVALUATION:
            if strategy.win_rate < self.MIN_WIN_RATE_THRESHOLD * 0.8:  # 20% below threshold
                if strategy.status == StrategyStatus.ACTIVE:
                    strategy.status = StrategyStatus.PAUSED
                    logger.warning(
                        f"Strategy {strategy_id} paused due to low win rate: {strategy.win_rate:.1%}"
                    )
    
    def activate_strategy(self, strategy_id: str) -> bool:
        """Manually activate a strategy"""
        if strategy_id not in self.strategies:
            return False
        
        strategy = self.strategies[strategy_id]
        if strategy.status != StrategyStatus.DISABLED:
            strategy.status = StrategyStatus.ACTIVE
            logger.info(f"Strategy {strategy_id} activated")
            return True
        return False
    
    def deactivate_strategy(self, strategy_id: str) -> bool:
        """Manually deactivate a strategy"""
        if strategy_id not in self.strategies:
            return False
        
        self.strategies[strategy_id].status = StrategyStatus.INACTIVE
        logger.info(f"Strategy {strategy_id} deactivated")
        return True
    
    def disable_strategy(self, strategy_id: str) -> bool:
        """Disable a strategy (won't be considered for allocation)"""
        if strategy_id not in self.strategies:
            return False
        
        self.strategies[strategy_id].status = StrategyStatus.DISABLED
        logger.info(f"Strategy {strategy_id} disabled")
        return True
    
    # =========================================================================
    # ML Model Management
    # =========================================================================
    
    def _load_ml_model(self):
        """Load ML model if available"""
        if not self.ml_model_path:
            logger.info("No ML model path configured, using fallback allocation")
            return
        
        if not os.path.exists(self.ml_model_path):
            logger.warning(f"ML model not found at {self.ml_model_path}, using fallback")
            return
        
        try:
            # Try to load model (implementation depends on model type)
            # This is a placeholder for actual model loading
            import pickle
            with open(self.ml_model_path, 'rb') as f:
                self.ml_model = pickle.load(f)
            self.ml_available = True
            logger.info(f"ML model loaded from {self.ml_model_path}")
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            self.ml_available = False
    
    def _prepare_ml_features(self) -> List[List[float]]:
        """Prepare features for ML model"""
        features = []
        
        for strategy in self.strategies.values():
            feature_vector = [
                strategy.win_rate,
                strategy.sharpe_ratio,
                strategy.profit_factor,
                strategy.max_drawdown_pct,
                strategy.volatility,
                strategy.recent_win_rate,
                strategy.current_consecutive_losses,
                strategy.total_trades,
            ]
            features.append(feature_vector)
        
        return features
    
    def _predictions_to_allocations(self, predictions) -> Dict[str, float]:
        """Convert ML predictions to allocations"""
        # Placeholder - actual implementation depends on model output
        strategy_ids = list(self.strategies.keys())
        allocations = {}
        
        for i, strategy_id in enumerate(strategy_ids):
            if i < len(predictions):
                allocations[strategy_id] = max(0, float(predictions[i]))
        
        # Normalize
        total = sum(allocations.values())
        if total > 0:
            allocations = {k: v / total for k, v in allocations.items()}
        
        return allocations
    
    # =========================================================================
    # Status and Reporting
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current Meta-Learner status"""
        return {
            "ml_available": self.ml_available,
            "risk_profile": self.risk_profile.value,
            "total_strategies": len(self.strategies),
            "active_strategies": len([s for s in self.strategies.values() if s.status == StrategyStatus.ACTIVE]),
            "strategies": {sid: s.to_dict() for sid, s in self.strategies.items()},
            "latest_allocation": self.allocation_history[-1].to_dict() if self.allocation_history else None,
        }
    
    def get_strategy_rankings(self) -> List[Dict[str, Any]]:
        """Get strategies ranked by score"""
        rankings = []
        
        for strategy_id, strategy in self.strategies.items():
            score = self._calculate_strategy_score(strategy_id)
            rankings.append({
                "strategy_id": strategy_id,
                "strategy_name": strategy.strategy_name,
                "score": score,
                "win_rate": strategy.win_rate,
                "sharpe_ratio": strategy.sharpe_ratio,
                "status": strategy.status.value,
                "allocation_pct": strategy.allocation_pct,
            })
        
        rankings.sort(key=lambda x: x["score"], reverse=True)
        return rankings
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def save_state(self):
        """Save Meta-Learner state to file"""
        state_file = os.path.join(self.data_dir, "meta_learner_state.json")
        
        data = {
            "risk_profile": self.risk_profile.value,
            "strategies": {sid: s.to_dict() for sid, s in self.strategies.items()},
            "allocation_history": [a.to_dict() for a in self.allocation_history[-20:]],
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        with open(state_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Meta-Learner state saved to {state_file}")
    
    def load_state(self) -> bool:
        """Load Meta-Learner state from file"""
        state_file = os.path.join(self.data_dir, "meta_learner_state.json")
        
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            # Restore risk profile
            self.risk_profile = RiskProfile(data.get("risk_profile", "moderate"))
            
            # Restore strategies (partial)
            for sid, sdata in data.get("strategies", {}).items():
                if sid in self.strategies:
                    strategy = self.strategies[sid]
                    strategy.total_trades = sdata.get("total_trades", 0)
                    strategy.winning_trades = sdata.get("winning_trades", 0)
                    strategy.losing_trades = sdata.get("losing_trades", 0)
                    strategy.total_pnl = sdata.get("total_pnl", 0.0)
                    strategy.win_rate = sdata.get("win_rate", 0.0)
            
            logger.info(f"Meta-Learner state loaded from {state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading Meta-Learner state: {e}")
            return False


# Singleton instance
_meta_learner_instance: Optional[MetaLearner] = None


def get_meta_learner(
    data_dir: str = "/app/data",
    risk_profile: RiskProfile = RiskProfile.MODERATE,
) -> MetaLearner:
    """Get or create the singleton MetaLearner instance"""
    global _meta_learner_instance
    
    if _meta_learner_instance is None:
        _meta_learner_instance = MetaLearner(
            data_dir=data_dir,
            risk_profile=risk_profile,
        )
    
    return _meta_learner_instance
