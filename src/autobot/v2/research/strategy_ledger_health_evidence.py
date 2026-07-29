"""Read-only strategy-health evidence from the official attributed ledger.

The strategy risk mandate layer deliberately stays independent from paper
runtime modules.  This adapter is the separate research boundary that turns
official *shadow* observations into conservative health facts for an audit.
It never creates orders, changes a ledger, authorizes paper capital, or
promotes a strategy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from autobot.v2.paper.official_performance import (
    OfficialPaperPerformanceConfig,
    build_official_paper_performance_report,
)

from .strategy_risk_mandates import StrategyHealthSnapshot


SHADOW_PAPER_MODE = "shadow_paper"


@dataclass(frozen=True)
class StrategyLedgerHealthEvidenceConfig:
    """Inputs for one read-only strategy-health audit."""

    state_db_path: Path
    registry_path: Path = Path("docs/research/strategy_hypotheses.json")
    strategy_id: str = ""
    min_closed_trades_for_health: int = 30
    initial_capital_eur: float = 1_000.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        strategy_id = str(self.strategy_id or "").strip()
        if not strategy_id:
            raise ValueError("strategy_id is required")
        if self.min_closed_trades_for_health < 1:
            raise ValueError("min_closed_trades_for_health must be at least 1")
        if not math.isfinite(float(self.initial_capital_eur)) or self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive and finite")
        generated_at = self.generated_at
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "generated_at", generated_at.astimezone(timezone.utc))


@dataclass(frozen=True)
class StrategyLedgerHealthEvidence:
    """A non-authorizing health snapshot with its exact ledger provenance."""

    strategy_id: str
    state_db_path: str
    registry_path: str
    generated_at: str
    source: str
    execution_mode: str
    min_closed_trades_for_health: int
    selected_metrics: dict[str, Any]
    selected_closed_trade_count: int
    paper_capital_trade_count_ignored: int
    health_metrics_applied: bool
    health: StrategyHealthSnapshot
    warnings: tuple[str, ...] = ()
    json_report_path: str | None = None
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    promotable: bool = False

    def __post_init__(self) -> None:
        if not str(self.strategy_id or "").strip():
            raise ValueError("strategy_id is required")
        if self.execution_mode != SHADOW_PAPER_MODE:
            raise ValueError("strategy health evidence must use shadow_paper observations only")
        if self.selected_closed_trade_count < 0 or self.paper_capital_trade_count_ignored < 0:
            raise ValueError("trade counts cannot be negative")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed or self.promotable:
            raise ValueError("strategy health evidence must remain research-only and non-promotional")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "state_db_path": self.state_db_path,
            "registry_path": self.registry_path,
            "generated_at": self.generated_at,
            "source": self.source,
            "execution_mode": self.execution_mode,
            "selection_policy": "official_attributed_shadow_paper_only",
            "min_closed_trades_for_health": self.min_closed_trades_for_health,
            "selected_metrics": dict(self.selected_metrics),
            "selected_closed_trade_count": self.selected_closed_trade_count,
            "paper_capital_trade_count_ignored": self.paper_capital_trade_count_ignored,
            "health_metrics_applied": self.health_metrics_applied,
            "health": asdict(self.health),
            "warnings": list(self.warnings),
            "json_report_path": self.json_report_path,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
            "safety_notes": [
                "Reads the state database through its read-only official ledger loader.",
                "Legacy and non-reportable ledger rows are excluded by the official performance report.",
                "Only shadow_paper metrics can affect the health snapshot.",
                "Paper-capital metrics, if present, are reported as ignored evidence.",
                "This audit can only support a risk reduction or block; it grants no execution permission.",
            ],
        }


def build_strategy_ledger_health_evidence(
    config: StrategyLedgerHealthEvidenceConfig,
) -> StrategyLedgerHealthEvidence:
    """Build a conservative health view without mutating the ledger or runtime.

    Insufficient, incomplete or ambiguous data never becomes a healthy metric.
    In particular, paper-capital rows are deliberately not merged with shadow
    observations: this command remains a research/shadow diagnostic.
    """

    report = build_official_paper_performance_report(
        OfficialPaperPerformanceConfig(
            state_db_path=config.state_db_path,
            registry_path=config.registry_path,
            initial_capital_eur=config.initial_capital_eur,
            generated_at=config.generated_at,
            run_id=f"strategy_ledger_health_{_safe_component(config.strategy_id)}",
        ),
        write_report=False,
    )
    summary = next((item for item in report.ranking if item.strategy_id == config.strategy_id), None)
    warnings = [f"ledger_loader:{warning}" for warning in report.warnings]
    shadow_metrics: dict[str, Any] = {}
    paper_capital_trade_count_ignored = 0
    if summary is None:
        warnings.append("strategy_missing_from_official_attributed_report")
    else:
        shadow_metrics = dict(summary.shadow_paper_metrics)
        paper_capital_trade_count_ignored = _trade_count(summary.paper_capital_metrics)
        if paper_capital_trade_count_ignored:
            warnings.append("paper_capital_metrics_ignored_for_research_shadow_health")

    selected_closed_trade_count = _trade_count(shadow_metrics)
    health, health_metrics_applied, health_warnings = _health_from_shadow_metrics(
        shadow_metrics,
        min_closed_trades_for_health=config.min_closed_trades_for_health,
    )
    warnings.extend(health_warnings)
    return StrategyLedgerHealthEvidence(
        strategy_id=config.strategy_id,
        state_db_path=str(config.state_db_path),
        registry_path=str(config.registry_path),
        generated_at=config.generated_at.isoformat(),
        source=report.source,
        execution_mode=SHADOW_PAPER_MODE,
        min_closed_trades_for_health=config.min_closed_trades_for_health,
        selected_metrics=shadow_metrics,
        selected_closed_trade_count=selected_closed_trade_count,
        paper_capital_trade_count_ignored=paper_capital_trade_count_ignored,
        health_metrics_applied=health_metrics_applied,
        health=health,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def write_strategy_ledger_health_evidence(
    evidence: StrategyLedgerHealthEvidence,
    output_dir: str | Path,
) -> StrategyLedgerHealthEvidence:
    """Optionally persist a compact audit artifact; the state DB remains read-only."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(evidence.generated_at.replace("Z", "+00:00")).strftime("%Y%m%d_%H%M%S")
    path = output / f"strategy_ledger_health_{_safe_component(evidence.strategy_id)}_{stamp}.json"
    persisted = replace(evidence, json_report_path=str(path))
    path.write_text(json.dumps(persisted.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return persisted


def _health_from_shadow_metrics(
    metrics: Mapping[str, Any],
    *,
    min_closed_trades_for_health: int,
) -> tuple[StrategyHealthSnapshot, bool, tuple[str, ...]]:
    closed_trade_count = _trade_count(metrics)
    if closed_trade_count < min_closed_trades_for_health:
        return (
            StrategyHealthSnapshot(),
            False,
            (f"insufficient_closed_trades_for_health:{closed_trade_count}/{min_closed_trades_for_health}",),
        )
    if metrics.get("fees_included") is not True or metrics.get("slippage_included") is not True:
        return StrategyHealthSnapshot(), False, ("cost_evidence_incomplete_for_health",)
    rolling_pf = _finite_number(metrics.get("profit_factor"))
    rolling_expectancy = _finite_number(metrics.get("expectancy_eur"))
    if rolling_pf is None or rolling_expectancy is None:
        return StrategyHealthSnapshot(), False, ("finite_pf_and_expectancy_required_for_health",)
    return (
        StrategyHealthSnapshot(
            rolling_pf=rolling_pf,
            rolling_expectancy=rolling_expectancy,
        ),
        True,
        (),
    )


def _trade_count(metrics: Mapping[str, Any]) -> int:
    value = _finite_number(metrics.get("closed_trade_count"))
    return max(0, int(value or 0))


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()) or "unknown"
