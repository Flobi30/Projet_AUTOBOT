"""Daily paper trading reporting engine for AUTOBOT.

This module does not replace the runtime `PaperTradingExecutor`. It creates a
daily operational report from the same research trade records and risk decision
contracts used by backtest/replay validation. The goal is paper/live parity:
paper decisions must be explainable, net of costs, and blocked when risk says
so.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from autobot.v2.research.metrics_engine import MetricsEngine, MetricsResult
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord
from autobot.v2.risk.risk_manager_v2 import RiskDecision


@dataclass(frozen=True)
class PaperDailyConfig:
    report_date: date
    run_id: str | None = None
    initial_capital_eur: float = 1_000.0
    output_dir: Path = Path("reports/paper")
    max_daily_loss_pct: float = 0.03
    strategy_disable_loss_pct: float = 0.02
    max_strategy_risk_rejections: int = 10

    def __post_init__(self) -> None:
        if self.initial_capital_eur <= 0.0:
            raise ValueError("initial_capital_eur must be positive")
        if self.max_daily_loss_pct <= 0.0:
            raise ValueError("max_daily_loss_pct must be positive")
        if self.strategy_disable_loss_pct <= 0.0:
            raise ValueError("strategy_disable_loss_pct must be positive")
        if self.max_strategy_risk_rejections <= 0:
            raise ValueError("max_strategy_risk_rejections must be positive")

    @property
    def resolved_run_id(self) -> str:
        return self.run_id or f"paper_daily_{self.report_date.isoformat()}"


@dataclass(frozen=True)
class PaperDecisionRecord:
    timestamp: datetime
    strategy_id: str
    symbol: str
    action: str
    status: str
    reason: str
    risk_blockers: tuple[str, ...] = ()
    risk_warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_risk_decision(
        cls,
        *,
        timestamp: datetime,
        strategy_id: str,
        symbol: str,
        action: str,
        decision: RiskDecision,
        metadata: dict[str, Any] | None = None,
    ) -> "PaperDecisionRecord":
        return cls(
            timestamp=_normalize_datetime(timestamp),
            strategy_id=strategy_id,
            symbol=symbol,
            action=action,
            status="accepted" if decision.approved else "risk_rejected",
            reason=decision.reason,
            risk_blockers=tuple(decision.blockers),
            risk_warnings=tuple(decision.warnings),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["risk_blockers"] = list(self.risk_blockers)
        data["risk_warnings"] = list(self.risk_warnings)
        return data


@dataclass(frozen=True)
class PaperStrategyDailyStatus:
    strategy_id: str
    trade_count: int
    net_pnl_eur: float
    gross_pnl_eur: float
    fees_eur: float
    spread_cost_eur: float
    slippage_eur: float
    winrate_pct: float | None
    profit_factor: float | None
    decision_count: int
    hold_count: int
    risk_rejection_count: int
    risk_rejection_reasons: dict[str, int]
    decision: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperDailyReport:
    run_id: str
    report_date: str
    mode: str
    generated_at: str
    initial_capital_eur: float
    metrics: MetricsResult
    trade_count: int
    decision_count: int
    hold_count: int
    risk_rejection_count: int
    risk_rejection_reasons: dict[str, int]
    errors: tuple[str, ...]
    strategy_statuses: tuple[PaperStrategyDailyStatus, ...]
    decision: str
    decision_reason: str
    json_report_path: str | None = None
    markdown_report_path: str | None = None
    safety_notes: tuple[str, ...] = field(
        default=(
            "Paper report only.",
            "No live trading permission is granted.",
            "No orders are created by this reporting engine.",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "report_date": self.report_date,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "initial_capital_eur": self.initial_capital_eur,
            "metrics": self.metrics.to_dict(),
            "trade_count": self.trade_count,
            "decision_count": self.decision_count,
            "hold_count": self.hold_count,
            "risk_rejection_count": self.risk_rejection_count,
            "risk_rejection_reasons": dict(self.risk_rejection_reasons),
            "errors": list(self.errors),
            "strategy_statuses": [status.to_dict() for status in self.strategy_statuses],
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "json_report_path": self.json_report_path,
            "markdown_report_path": self.markdown_report_path,
            "safety_notes": list(self.safety_notes),
        }


class PaperTradingEngine:
    """Build daily paper reports from closed trades and recorded decisions."""

    def __init__(self, config: PaperDailyConfig, *, metrics_engine: MetricsEngine | None = None) -> None:
        self.config = config
        self.metrics_engine = metrics_engine or MetricsEngine()

    def build_daily_report(
        self,
        journal: TradeJournal | Iterable[TradeRecord],
        decisions: Iterable[PaperDecisionRecord] = (),
        *,
        errors: Iterable[str] = (),
        write_report: bool = True,
    ) -> PaperDailyReport:
        records = tuple(journal.records if isinstance(journal, TradeJournal) else tuple(journal))
        daily_trades = tuple(trade for trade in records if trade.closed_at.date() == self.config.report_date)
        daily_decisions = tuple(
            decision for decision in decisions if decision.timestamp.date() == self.config.report_date
        )
        metrics = self.metrics_engine.calculate(
            daily_trades,
            initial_capital_eur=self.config.initial_capital_eur,
            baseline_name="no_trade",
            baseline_return_pct=0.0,
        )
        risk_reasons = _risk_reasons(daily_decisions)
        strategy_statuses = self._strategy_statuses(daily_trades, daily_decisions)
        decision, reason = self._daily_decision(metrics, strategy_statuses, tuple(errors))
        report = PaperDailyReport(
            run_id=self.config.resolved_run_id,
            report_date=self.config.report_date.isoformat(),
            mode="paper",
            generated_at=datetime.now(timezone.utc).isoformat(),
            initial_capital_eur=self.config.initial_capital_eur,
            metrics=metrics,
            trade_count=len(daily_trades),
            decision_count=len(daily_decisions),
            hold_count=sum(1 for item in daily_decisions if item.action.lower() == "hold"),
            risk_rejection_count=sum(1 for item in daily_decisions if item.status == "risk_rejected"),
            risk_rejection_reasons=dict(risk_reasons),
            errors=tuple(errors),
            strategy_statuses=strategy_statuses,
            decision=decision,
            decision_reason=reason,
        )
        if write_report:
            return write_paper_daily_report(report, self.config.output_dir)
        return report

    def _strategy_statuses(
        self,
        trades: Sequence[TradeRecord],
        decisions: Sequence[PaperDecisionRecord],
    ) -> tuple[PaperStrategyDailyStatus, ...]:
        strategy_ids = sorted({trade.strategy_id for trade in trades} | {decision.strategy_id for decision in decisions})
        statuses: list[PaperStrategyDailyStatus] = []
        for strategy_id in strategy_ids:
            strategy_trades = tuple(trade for trade in trades if trade.strategy_id == strategy_id)
            strategy_decisions = tuple(decision for decision in decisions if decision.strategy_id == strategy_id)
            metrics = self.metrics_engine.calculate(
                strategy_trades,
                initial_capital_eur=self.config.initial_capital_eur,
                baseline_name="no_trade",
                baseline_return_pct=0.0,
            )
            risk_reasons = _risk_reasons(strategy_decisions)
            risk_rejection_count = sum(1 for item in strategy_decisions if item.status == "risk_rejected")
            hold_count = sum(1 for item in strategy_decisions if item.action.lower() == "hold")
            decision, reason = self._strategy_decision(metrics, risk_rejection_count)
            statuses.append(
                PaperStrategyDailyStatus(
                    strategy_id=strategy_id,
                    trade_count=len(strategy_trades),
                    net_pnl_eur=metrics.total_net_pnl_eur,
                    gross_pnl_eur=metrics.total_gross_pnl_eur,
                    fees_eur=metrics.total_fees_eur,
                    spread_cost_eur=metrics.total_spread_cost_eur,
                    slippage_eur=metrics.total_slippage_eur,
                    winrate_pct=metrics.winrate_pct,
                    profit_factor=metrics.profit_factor,
                    decision_count=len(strategy_decisions),
                    hold_count=hold_count,
                    risk_rejection_count=risk_rejection_count,
                    risk_rejection_reasons=dict(risk_reasons),
                    decision=decision,
                    reason=reason,
                )
            )
        return tuple(statuses)

    def _strategy_decision(self, metrics: MetricsResult, risk_rejection_count: int) -> tuple[str, str]:
        loss_limit = -(self.config.initial_capital_eur * self.config.strategy_disable_loss_pct)
        if metrics.total_net_pnl_eur <= loss_limit and metrics.closed_trade_count > 0:
            return "DISABLE_STRATEGY", "strategy_daily_loss_limit_reached"
        if risk_rejection_count >= self.config.max_strategy_risk_rejections:
            return "DISABLE_STRATEGY", "strategy_risk_rejection_limit_reached"
        return "CONTINUE", "strategy_within_daily_limits"

    def _daily_decision(
        self,
        metrics: MetricsResult,
        strategy_statuses: Sequence[PaperStrategyDailyStatus],
        errors: Sequence[str],
    ) -> tuple[str, str]:
        if errors:
            return "PAUSE", "paper_errors_present"
        daily_loss_limit = -(self.config.initial_capital_eur * self.config.max_daily_loss_pct)
        if metrics.total_net_pnl_eur <= daily_loss_limit and metrics.closed_trade_count > 0:
            return "PAUSE", "max_daily_loss_reached"
        if any(status.decision == "DISABLE_STRATEGY" for status in strategy_statuses):
            return "DISABLE_STRATEGY", "one_or_more_strategies_breached_daily_limits"
        return "CONTINUE", "paper_within_daily_limits"


def write_paper_daily_report(report: PaperDailyReport, output_dir: str | Path) -> PaperDailyReport:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"daily_{report.report_date}.json"
    md_path = output_path / f"daily_{report.report_date}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_paper_daily_report(report), encoding="utf-8")
    return replace(report, json_report_path=str(json_path), markdown_report_path=str(md_path))


def render_paper_daily_report(report: PaperDailyReport) -> str:
    lines = [
        f"# Paper Daily Report - {report.report_date}",
        "",
        f"Run id: `{report.run_id}`",
        f"Mode: `{report.mode}`",
        f"Decision: `{report.decision}`",
        f"Reason: `{report.decision_reason}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Net PnL EUR | {report.metrics.total_net_pnl_eur:.6f} |",
        f"| Gross PnL EUR | {report.metrics.total_gross_pnl_eur:.6f} |",
        f"| Fees EUR | {report.metrics.total_fees_eur:.6f} |",
        f"| Spread Cost EUR | {report.metrics.total_spread_cost_eur:.6f} |",
        f"| Slippage EUR | {report.metrics.total_slippage_eur:.6f} |",
        f"| Max Drawdown % | {report.metrics.max_drawdown_pct:.6f} |",
        f"| Profit Factor | {_fmt(report.metrics.profit_factor)} |",
        f"| Winrate % | {_fmt(report.metrics.winrate_pct)} |",
        f"| Closed Trades | {report.trade_count} |",
        f"| Decisions | {report.decision_count} |",
        f"| HOLD Decisions | {report.hold_count} |",
        f"| Risk Rejections | {report.risk_rejection_count} |",
        "",
        "## Strategies",
        "",
        "| Strategy | Decision | Reason | Trades | Net PnL | PF | Risk Rejections | HOLD |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for status in report.strategy_statuses:
        lines.append(
            f"| {status.strategy_id} | {status.decision} | {status.reason} | {status.trade_count} | "
            f"{status.net_pnl_eur:.6f} | {_fmt(status.profit_factor)} | "
            f"{status.risk_rejection_count} | {status.hold_count} |"
        )
    lines.extend(["", "## Risk Rejection Reasons", ""])
    if report.risk_rejection_reasons:
        for reason, count in sorted(report.risk_rejection_reasons.items()):
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "## Errors", ""])
    if report.errors:
        lines.extend(f"- {error}" for error in report.errors)
    else:
        lines.append("- None")
    lines.extend(["", "## Safety", ""])
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _risk_reasons(decisions: Iterable[PaperDecisionRecord]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for decision in decisions:
        if decision.status != "risk_rejected":
            continue
        if decision.risk_blockers:
            counter.update(decision.risk_blockers)
        else:
            counter[decision.reason] += 1
    return counter


def _normalize_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
