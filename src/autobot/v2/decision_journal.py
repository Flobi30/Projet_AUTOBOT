"""Decision Journal (Lot 1): lightweight append-only structured decision logging.

Purpose: explainability/observability for major runtime decisions only.
Default-safe behavior: disabled unless explicitly enabled by feature flag.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REJECTION_REASON_RANKING_BELOW_THRESHOLD = "ranking_below_threshold"
REJECTION_REASON_SCALABILITY_GUARD_BLOCK = "scalability_guard_block"
REJECTION_REASON_VALIDATION_GUARD_BLOCK = "validation_guard_block"
REJECTION_REASON_REPEATED_AUTO_ACTION_BLOCK = "repeated_auto_action_block"
REJECTION_REASON_BLACK_SWAN_EMERGENCY_BLOCK = "black_swan_emergency_block"
REJECTION_REASON_ALLOCATION_ENVELOPE_BLOCKED = "allocation_envelope_blocked"
REJECTION_REASON_SYMBOL_NOT_SELECTED = "symbol_not_selected_not_activated"


class DecisionJournal:
    """Append-only JSONL decision journal.

    Records only major decisions. Each record keeps a stable schema to support
    post-run analytics and operator review.
    """

    def __init__(
        self,
        enabled: bool,
        journal_path: str,
        runtime_context: Optional[Dict[str, Any]] = None,
        flush_every: int = 1,
    ) -> None:
        self.enabled = bool(enabled)
        self.path = Path(journal_path)
        self.runtime_context = dict(runtime_context or {})
        self.flush_every = max(1, int(flush_every))

        self._lock = threading.Lock()
        self._buffered = 0
        self._fh = None

        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.flush()
                self._fh.close()
                self._fh = None

    def log(
        self,
        *,
        decision_type: str,
        source: str,
        reasons: Optional[Iterable[str]] = None,
        symbols: Optional[Iterable[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Write one decision record (append-only JSONL).

        Returns True when written, False when disabled.
        """
        if not self.enabled or self._fh is None:
            return False

        rec = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision_type": str(decision_type),
            "source": str(source),
            "symbols": [str(s) for s in (symbols or [])],
            "reasons": [str(r) for r in (reasons or [])],
            "context": dict(context or {}),
            "runtime": dict(self.runtime_context),
        }
        if session_id:
            rec["session_id"] = str(session_id)

        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._fh.write(line + "\n")
            self._buffered += 1
            if self._buffered >= self.flush_every:
                self._fh.flush()
                self._buffered = 0
        return True


def journal_from_env() -> DecisionJournal:
    """Construct journal from environment feature flags."""
    enabled = os.getenv("ENABLE_DECISION_JOURNAL", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    path = os.getenv("DECISION_JOURNAL_PATH", "data/decision_journal.jsonl")
    flush_every = int(os.getenv("DECISION_JOURNAL_FLUSH_EVERY", "1"))
    context = {
        "deployment_stage": os.getenv("DEPLOYMENT_STAGE", "paper"),
        "paper_trading": os.getenv("PAPER_TRADING", "false").strip().lower() in {"1", "true", "yes", "on"},
        "pid": os.getpid(),
    }
    return DecisionJournal(enabled=enabled, journal_path=path, runtime_context=context, flush_every=flush_every)


def build_rejected_opportunity_report(
    *,
    journal_path: str,
    window_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate rejected opportunity records by reason and symbol."""
    now = datetime.now(timezone.utc)
    cutoff = None
    if window_hours is not None and int(window_hours) > 0:
        cutoff = now.timestamp() - (int(window_hours) * 3600)

    rows: List[Dict[str, Any]] = []
    path = Path(journal_path)
    if not path.exists():
        return {
            "generated_at": now.isoformat(),
            "window_hours": int(window_hours) if window_hours is not None else None,
            "total_rejections": 0,
            "by_reason": {},
            "by_symbol": {},
            "reason_symbol": {},
            "records": [],
        }

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("decision_type") != "rejected_opportunity":
            continue
        ts = str(rec.get("timestamp") or "")
        include = True
        if cutoff is not None and ts:
            try:
                dts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                include = dts.timestamp() >= cutoff
            except Exception:
                include = True
        if include:
            rows.append(rec)

    by_reason: Dict[str, int] = {}
    by_symbol: Dict[str, int] = {}
    reason_symbol: Dict[str, int] = {}
    for rec in rows:
        reasons = rec.get("reasons") or []
        reason = str(reasons[0]) if reasons else "unknown"
        symbols = rec.get("symbols") or []
        symbol = str(symbols[0]) if symbols else "UNKNOWN"
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        key = f"{reason}::{symbol}"
        reason_symbol[key] = reason_symbol.get(key, 0) + 1

    return {
        "generated_at": now.isoformat(),
        "window_hours": int(window_hours) if window_hours is not None else None,
        "total_rejections": len(rows),
        "by_reason": dict(sorted(by_reason.items(), key=lambda kv: kv[1], reverse=True)),
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda kv: kv[1], reverse=True)),
        "reason_symbol": dict(sorted(reason_symbol.items(), key=lambda kv: kv[1], reverse=True)),
        "records": rows[-200:],
    }
