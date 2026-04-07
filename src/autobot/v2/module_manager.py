"""
ModuleManager -- Conditional activation and lifecycle for all AUTOBOT modules.

Reads MODULE_* env vars. Provides init/start/stop for the orchestrator.
Each module is wrapped in try/except so failures are non-fatal.
"""
from __future__ import annotations
import asyncio, logging, os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, str(default)).lower().strip()
    return val in ("true", "1", "yes", "on")

class ModuleManager:
    def __init__(self) -> None:
        self._modules: Dict[str, Any] = {}
        self._started: bool = False
        # Defaults: safe=ON, experimental/risky=OFF
        self.config = {
            "shadow_trading":    _env_bool("MODULE_SHADOW_TRADING", False),
            "daily_reporter":    _env_bool("MODULE_DAILY_REPORTER", True),
            "rebalance_manager": _env_bool("MODULE_REBALANCE_MANAGER", True),
            "auto_evolution":    _env_bool("MODULE_AUTO_EVOLUTION", True),
            "market_analyzer":   _env_bool("MODULE_MARKET_ANALYZER", True),
            "strategy_ensemble": _env_bool("MODULE_STRATEGY_ENSEMBLE", True),
            "trailing_stop_atr":     _env_bool("MODULE_TRAILING_STOP_ATR", True),
            "volatility_weighter":   _env_bool("MODULE_VOLATILITY_WEIGHTER", True),
            "regime_detector":       _env_bool("MODULE_REGIME_DETECTOR", True),
            "atr_filter":            _env_bool("MODULE_ATR_FILTER", True),
            "kelly_criterion":       _env_bool("MODULE_KELLY_CRITERION", True),
            "fee_optimizer":         _env_bool("MODULE_FEE_OPTIMIZER", True),
            "rate_limit_optimizer":  _env_bool("MODULE_RATE_LIMIT_OPTIMIZER", True),
            "pyramiding_manager":    _env_bool("MODULE_PYRAMIDING_MANAGER", False),
            "xgboost_predictor":     _env_bool("MODULE_XGBOOST_PREDICTOR", False),
            "pairs_trading":         _env_bool("MODULE_PAIRS_TRADING", False),
            "momentum_scoring":      _env_bool("MODULE_MOMENTUM_SCORING", True),
            "multi_indicator_vote":  _env_bool("MODULE_MULTI_INDICATOR_VOTE", True),
            "liquidation_heatmap":   _env_bool("MODULE_LIQUIDATION_HEATMAP", False),
            "black_swan":            _env_bool("MODULE_BLACK_SWAN", True),
            "vwap_twap":             _env_bool("MODULE_VWAP_TWAP", False),
            "dca_hybrid":            _env_bool("MODULE_DCA_HYBRID", False),
            "micro_grid":            _env_bool("MODULE_MICRO_GRID", False),
            "sentiment_nlp":         _env_bool("MODULE_SENTIMENT_NLP", False),
            "heuristic_predictor":   _env_bool("MODULE_HEURISTIC_PREDICTOR", False),
            "onchain_data":          _env_bool("MODULE_ONCHAIN_DATA", False),
            "mean_reversion":        _env_bool("MODULE_MEAN_REVERSION", False),
            "triangular_arbitrage":  _env_bool("MODULE_TRIANGULAR_ARBITRAGE", False),
        }
        enabled = [k for k, v in self.config.items() if v]
        logger.info("ModuleManager: %d enabled, %d disabled", len(enabled), len(self.config) - len(enabled))
        if enabled:
            logger.info("  Enabled: %s", ", ".join(enabled))

    def get(self, name: str) -> Optional[Any]:
        return self._modules.get(name)

    def is_loaded(self, name: str) -> bool:
        return name in self._modules

    @property
    def loaded_modules(self) -> List[str]:
        return list(self._modules.keys())

    def get_status(self) -> Dict[str, Any]:
        return {
            "total_configured": len(self.config),
            "total_enabled": sum(1 for v in self.config.values() if v),
            "total_loaded": len(self._modules),
            "started": self._started,
            "modules": {n: {"enabled": self.config.get(n, False), "loaded": n in self._modules} for n in self.config},
        }

    def _try_init(self, name: str, factory) -> None:
        try:
            mod = factory()
            if mod is not None:
                self._modules[name] = mod
                logger.info("  [OK] %s", name)
        except Exception as exc:
            logger.warning("  [FAIL] %s: %s", name, exc)

    def init_modules(self, orchestrator: Any) -> None:
        logger.info("Initializing enabled modules...")
        c = self.config

        if c["shadow_trading"]:
            def f():
                from .shadow_trading import ShadowTradingManager
                return ShadowTradingManager()
            self._try_init("shadow_trading", f)

        if c["daily_reporter"]:
            def f():
                from .reports import DailyReporter
                return DailyReporter(orchestrator)
            self._try_init("daily_reporter", f)

        if c["rebalance_manager"]:
            def f():
                from .rebalance_manager import RebalanceManager
                return RebalanceManager(orchestrator)
            self._try_init("rebalance_manager", f)

        if c["auto_evolution"]:
            def f():
                from .auto_evolution import AutoEvolutionManager
                return AutoEvolutionManager(db_path=os.getenv("AUTOEVOLUTION_DB", "data/autoevolution.db"))
            self._try_init("auto_evolution", f)

        if c["market_analyzer"]:
            def f():
                from .market_analyzer import MarketAnalyzer
                return MarketAnalyzer()
            self._try_init("market_analyzer", f)

        if c["strategy_ensemble"]:
            def f():
                from .strategy_ensemble import StrategyEnsemble
                return StrategyEnsemble()
            self._try_init("strategy_ensemble", f)

        if c["trailing_stop_atr"]:
            def f():
                from .modules.trailing_stop_atr import TrailingStopATR
                return TrailingStopATR()
            self._try_init("trailing_stop_atr", f)

        if c["volatility_weighter"]:
            def f():
                from .modules.volatility_weighter import VolatilityWeighter
                return VolatilityWeighter()
            self._try_init("volatility_weighter", f)

        if c["regime_detector"]:
            def f():
                from .modules.regime_detector import RegimeDetector
                return RegimeDetector()
            self._try_init("regime_detector", f)

        if c["atr_filter"]:
            def f():
                from .modules.atr_filter import ATRFilter
                return ATRFilter()
            self._try_init("atr_filter", f)

        if c["kelly_criterion"]:
            def f():
                from .modules.kelly_criterion import KellyCriterion
                return KellyCriterion()
            self._try_init("kelly_criterion", f)

        if c["fee_optimizer"]:
            def f():
                from .modules.fee_optimizer import FeeOptimizer
                return FeeOptimizer()
            self._try_init("fee_optimizer", f)

        if c["rate_limit_optimizer"]:
            def f():
                from .modules.rate_limit_optimizer import RateLimitOptimizer
                return RateLimitOptimizer()
            self._try_init("rate_limit_optimizer", f)

        if c["pyramiding_manager"]:
            def f():
                from .modules.pyramiding_manager import PyramidingManager
                return PyramidingManager()
            self._try_init("pyramiding_manager", f)

        if c["xgboost_predictor"]:
            def f():
                from .modules.xgboost_predictor import XGBoostPredictor
                return XGBoostPredictor()
            self._try_init("xgboost_predictor", f)

        if c["pairs_trading"]:
            def f():
                from .modules.pairs_trading import PairsTrader
                return PairsTrader(pair_a=os.getenv("PAIRS_TRADING_A", "XBT/EUR"), pair_b=os.getenv("PAIRS_TRADING_B", "ETH/EUR"))
            self._try_init("pairs_trading", f)

        if c["momentum_scoring"]:
            def f():
                from .modules.momentum_scoring import MomentumScorer
                return MomentumScorer()
            self._try_init("momentum_scoring", f)

        if c["multi_indicator_vote"]:
            def f():
                from .modules.multi_indicator_vote import MultiIndicatorVoter
                return MultiIndicatorVoter()
            self._try_init("multi_indicator_vote", f)

        if c["liquidation_heatmap"]:
            def f():
                from .modules.liquidation_heatmap import LiquidationHeatmap
                return LiquidationHeatmap()
            self._try_init("liquidation_heatmap", f)

        if c["black_swan"]:
            def f():
                from .modules.black_swan import BlackSwanCatcher
                return BlackSwanCatcher()
            self._try_init("black_swan", f)

        if c["vwap_twap"]:
            def f():
                from .modules.vwap_twap import VWAPTWAPEngine
                return VWAPTWAPEngine()
            self._try_init("vwap_twap", f)

        if c["dca_hybrid"]:
            def f():
                from .modules.dca_hybrid import DCAHybridGrid
                return DCAHybridGrid()
            self._try_init("dca_hybrid", f)

        if c["micro_grid"]:
            def f():
                from .modules.micro_grid import MicroGridScalper
                return MicroGridScalper()
            self._try_init("micro_grid", f)

        if c["sentiment_nlp"]:
            def f():
                from .modules.sentiment_nlp import SentimentAnalyzer
                return SentimentAnalyzer()
            self._try_init("sentiment_nlp", f)

        if c["heuristic_predictor"]:
            def f():
                from .modules.cnn_lstm_predictor import HeuristicPredictor
                return HeuristicPredictor()
            self._try_init("heuristic_predictor", f)

        if c["onchain_data"]:
            def f():
                from .modules.onchain_data import OnchainDataModule
                return OnchainDataModule()
            self._try_init("onchain_data", f)

        if c["mean_reversion"]:
            def f():
                from .strategies.mean_reversion import MeanReversionStrategy
                return MeanReversionStrategy()
            self._try_init("mean_reversion", f)

        if c["triangular_arbitrage"]:
            def f():
                from .strategies.arbitrage import TriangularArbitrage
                return TriangularArbitrage(pairs=os.getenv("ARBITRAGE_PAIRS", "BTC/EUR,ETH/BTC,ETH/EUR").split(","))
            self._try_init("triangular_arbitrage", f)

        logger.info("Module init complete: %d/%d loaded", len(self._modules), sum(1 for v in c.values() if v))

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for name, mod in self._modules.items():
            if hasattr(mod, "start"):
                try:
                    result = mod.start()
                    if asyncio.iscoroutine(result):
                        await result
                    logger.info("  Started: %s", name)
                except Exception as exc:
                    logger.warning("  Failed to start %s: %s", name, exc)

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        for name in reversed(list(self._modules.keys())):
            mod = self._modules[name]
            if hasattr(mod, "stop"):
                try:
                    result = mod.stop()
                    if asyncio.iscoroutine(result):
                        await result
                    logger.info("  Stopped: %s", name)
                except Exception as exc:
                    logger.warning("  Failed to stop %s: %s", name, exc)
