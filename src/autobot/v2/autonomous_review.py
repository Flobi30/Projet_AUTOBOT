"""Autonomous analytical review (recommendation-first, analytics-only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .consolidated_review import build_consolidated_profitability_review


def _read_journal_rows(journal_path: str, window_hours: Optional[int]) -> List[Dict[str, Any]]:
    path = Path(journal_path)
    if not path.exists():
        return []

    cutoff = None
    now = datetime.now(timezone.utc).timestamp()
    if window_hours is not None and int(window_hours) > 0:
        cutoff = now - int(window_hours) * 3600

    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        if cutoff is not None:
            ts = str(rec.get("timestamp") or "")
            if ts:
                try:
                    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if d.timestamp() < cutoff:
                        continue
                except Exception:
                    pass
        rows.append(rec)
    return rows


def _health_level(total_trades: int, net_pnl: float, guard_events: int, rejected_total: int) -> str:
    if total_trades == 0:
        return "degraded"
    if net_pnl < 0 and guard_events > 0:
        return "critical"
    if net_pnl < 0 or rejected_total > (total_trades * 2):
        return "degraded"
    return "stable"


def _recommended_action(total_trades: int, net_pnl: float, winners: int, losers: int, health: str) -> str:
    if health == "critical":
        return "inspect"
    if total_trades == 0:
        return "inspect"
    if net_pnl < 0:
        return "reduce"
    if net_pnl > 0 and winners >= 2 and losers == 0:
        return "expand"
    return "hold"


def _confidence(total_trades: int, decision_records: int) -> float:
    base = min(1.0, (total_trades / 30.0)) * 0.6 + min(1.0, decision_records / 50.0) * 0.4
    return round(max(0.2, min(0.95, base)), 2)


def build_autonomous_review(
    *,
    db_path: str,
    journal_path: str,
    window_hours: Optional[int] = None,
    pair_limit: int = 20,
) -> Dict[str, Any]:
    consolidated = build_consolidated_profitability_review(
        db_path=db_path,
        journal_path=journal_path,
        window_hours=window_hours,
        pair_limit=pair_limit,
    )

    pair_report = consolidated.get("pair_performance_attribution", {})
    pairs = pair_report.get("pairs", [])
    totals = pair_report.get("totals", {})
    total_trades = int(totals.get("total_trades", 0))
    net_pnl = float(totals.get("total_realized_pnl", 0.0))

    top_pairs = [p for p in pairs if float(p.get("total_realized_pnl", 0.0)) > 0][:3]
    under_pairs = sorted(
        [p for p in pairs if float(p.get("total_realized_pnl", 0.0)) < 0],
        key=lambda p: float(p.get("total_realized_pnl", 0.0)),
    )[:3]

    rejected = consolidated.get("rejected_opportunity_analytics", {})
    dominant_rejections = list(rejected.get("by_reason", {}).items())[:3]

    journal_rows = _read_journal_rows(journal_path, window_hours)
    guard_events = sum(
        1 for r in journal_rows
        if str(r.get("decision_type")) in {"guard_decision", "guard_force_reduce"}
        or "scalability_guard" in str(r.get("source", ""))
    )
    allocation_events = sum(
        1 for r in journal_rows
        if str(r.get("decision_type")) == "allocation_decision"
        or str(r.get("source", "")) == "portfolio_allocator"
        or (r.get("reasons") and "allocation_envelope_blocked" in [str(x) for x in r.get("reasons", [])])
    )

    health = _health_level(total_trades, net_pnl, guard_events, int(rejected.get("total_rejections", 0)))
    winners = len(top_pairs)
    losers = len(under_pairs)
    action = _recommended_action(total_trades, net_pnl, winners, losers, health)

    focus: List[str] = []
    if total_trades == 0:
        focus.append("No realized trades detected: inspect run activity, market connectivity, and entry gates.")
    if net_pnl < 0:
        focus.append("Net realized PnL is negative: inspect underperforming pairs and position sizing discipline.")
    if dominant_rejections:
        focus.append(f"Dominant rejection reason: {dominant_rejections[0][0]} ({dominant_rejections[0][1]}x).")
    if guard_events > 0:
        focus.append("Guard activity is non-zero: review scalability/kill-switch/reconciliation pressure.")
    if allocation_events > 0:
        focus.append("Allocation decisions are active: review envelope constraints and risk-budget usage.")
    if not focus:
        focus.append("System looks stable: maintain current setup and continue monitoring pair/rejection concentration.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": int(window_hours) if window_hours is not None else None,
        "global_system_health": health,
        "top_performing_pairs": top_pairs,
        "underperforming_pairs": under_pairs,
        "dominant_rejection_reasons": [{"reason": k, "count": v} for k, v in dominant_rejections],
        "scaling_guard_behavior_summary": {
            "guard_event_count": int(guard_events),
        },
        "allocation_behavior_clues": {
            "allocation_related_event_count": int(allocation_events),
        },
        "recommended_action": action,
        "recommended_focus_points": focus,
        "confidence_level": _confidence(total_trades=total_trades, decision_records=len(journal_rows)),
        "source_snapshot": {
            "decision_records": len(journal_rows),
            "realized_trades": total_trades,
            "rejected_total": int(rejected.get("total_rejections", 0)),
        },
    }
