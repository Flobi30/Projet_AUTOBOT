"""Research trade journal for replay/backtest validation runs."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class TradeRecord:
    run_id: str
    strategy_id: str
    symbol: str
    side: str
    opened_at: datetime
    closed_at: datetime
    quantity: float
    entry_price: float
    exit_price: float
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float = 0.0
    slippage_eur: float = 0.0
    spread_cost_eur: float = 0.0
    latency_cost_eur: float = 0.0
    entry_reason: str = ""
    exit_reason: str = ""
    regime: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.closed_at - self.opened_at).total_seconds())

    @property
    def is_win(self) -> bool:
        return self.net_pnl_eur > 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["opened_at"] = self.opened_at.isoformat()
        data["closed_at"] = self.closed_at.isoformat()
        data["duration_seconds"] = self.duration_seconds
        return data

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "TradeRecord":
        return cls(
            run_id=str(row["run_id"]),
            strategy_id=str(row["strategy_id"]),
            symbol=str(row["symbol"]),
            side=str(row["side"]).lower(),
            opened_at=_parse_timestamp(row["opened_at"]),
            closed_at=_parse_timestamp(row["closed_at"]),
            quantity=float(row["quantity"]),
            entry_price=float(row["entry_price"]),
            exit_price=float(row["exit_price"]),
            gross_pnl_eur=float(row["gross_pnl_eur"]),
            net_pnl_eur=float(row["net_pnl_eur"]),
            fees_eur=float(row.get("fees_eur") or 0.0),
            slippage_eur=float(row.get("slippage_eur") or 0.0),
            spread_cost_eur=float(row.get("spread_cost_eur") or 0.0),
            latency_cost_eur=float(row.get("latency_cost_eur") or 0.0),
            entry_reason=str(row.get("entry_reason") or ""),
            exit_reason=str(row.get("exit_reason") or ""),
            regime=str(row["regime"]) if row.get("regime") not in (None, "") else None,
            metadata=dict(row.get("metadata") or {}),
        )


class TradeJournal:
    """In-memory journal with deterministic JSON/CSV export helpers."""

    CSV_FIELDS = [
        "run_id",
        "strategy_id",
        "symbol",
        "side",
        "opened_at",
        "closed_at",
        "duration_seconds",
        "quantity",
        "entry_price",
        "exit_price",
        "gross_pnl_eur",
        "net_pnl_eur",
        "fees_eur",
        "slippage_eur",
        "spread_cost_eur",
        "latency_cost_eur",
        "entry_reason",
        "exit_reason",
        "regime",
        "metadata",
    ]

    def __init__(self, records: Iterable[TradeRecord] | None = None) -> None:
        self._records: list[TradeRecord] = []
        if records:
            self.extend(records)

    @property
    def records(self) -> tuple[TradeRecord, ...]:
        return tuple(self._records)

    def add(self, record: TradeRecord) -> None:
        self._validate(record)
        self._records.append(record)
        self._records.sort(key=lambda trade: (trade.closed_at, trade.opened_at, trade.symbol))

    def extend(self, records: Iterable[TradeRecord]) -> None:
        for record in records:
            self.add(record)

    def filter(
        self,
        *,
        strategy_id: str | None = None,
        symbol: str | None = None,
        run_id: str | None = None,
    ) -> list[TradeRecord]:
        return [
            trade
            for trade in self._records
            if (strategy_id is None or trade.strategy_id == strategy_id)
            and (symbol is None or trade.symbol == symbol)
            and (run_id is None or trade.run_id == run_id)
        ]

    def equity_curve(self, initial_capital_eur: float) -> list[tuple[datetime, float]]:
        equity = float(initial_capital_eur)
        curve: list[tuple[datetime, float]] = []
        for trade in self._records:
            equity += trade.net_pnl_eur
            curve.append((trade.closed_at, equity))
        return curve

    def to_json(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([trade.to_dict() for trade in self._records], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return output

    @classmethod
    def from_json(cls, path: str | Path) -> "TradeJournal":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("trade journal JSON must contain a list")
        return cls(TradeRecord.from_mapping(dict(row)) for row in payload)

    def to_csv(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            for trade in self._records:
                row = trade.to_dict()
                row["metadata"] = json.dumps(row["metadata"], sort_keys=True)
                writer.writerow(row)
        return output

    @staticmethod
    def _validate(record: TradeRecord) -> None:
        if record.quantity <= 0.0:
            raise ValueError("quantity must be positive")
        if record.entry_price <= 0.0 or record.exit_price <= 0.0:
            raise ValueError("entry and exit prices must be positive")
        if record.closed_at < record.opened_at:
            raise ValueError("closed_at cannot be before opened_at")
        if record.side not in {"buy", "sell", "long", "short"}:
            raise ValueError("side must be buy/sell/long/short")


def journal_from_records(records: Sequence[TradeRecord]) -> TradeJournal:
    return TradeJournal(records)
