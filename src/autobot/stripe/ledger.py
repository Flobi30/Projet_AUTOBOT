"""
AUTOBOT Stripe Ledger Module

Implements double-entry bookkeeping for all Stripe transactions.
Every transaction creates balanced debit/credit entries.
"""

import os
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class LedgerEntryType(Enum):
    """Types of ledger entries"""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    REFUND = "refund"
    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"
    TRADE_PROFIT = "trade_profit"
    TRADE_LOSS = "trade_loss"


class AccountType(Enum):
    """Account types for double-entry bookkeeping"""
    STRIPE_BALANCE = "stripe_balance"  # Asset: Money in Stripe
    USER_EQUITY = "user_equity"  # Equity: User's capital
    TRADING_ACCOUNT = "trading_account"  # Asset: Funds allocated to trading
    FEE_EXPENSE = "fee_expense"  # Expense: Stripe fees
    REVENUE = "revenue"  # Revenue: Trading profits
    PENDING = "pending"  # Liability: Pending transactions


@dataclass
class LedgerEntry:
    """A single ledger entry (one side of a double-entry transaction)"""
    id: str
    transaction_id: str  # Groups debit/credit pairs
    entry_type: str
    account: str
    debit: float  # Money coming in
    credit: float  # Money going out
    balance_after: float
    stripe_tx_id: Optional[str]  # Stripe transaction ID for reconciliation
    description: str
    metadata: Dict[str, Any]
    created_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LedgerEntry':
        return cls(**data)


@dataclass
class Transaction:
    """A complete transaction with balanced debit/credit entries"""
    id: str
    tx_type: str
    amount: float
    currency: str
    stripe_tx_id: Optional[str]
    entries: List[LedgerEntry]
    status: str  # pending, completed, failed, reconciled
    created_at: str
    reconciled_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tx_type": self.tx_type,
            "amount": self.amount,
            "currency": self.currency,
            "stripe_tx_id": self.stripe_tx_id,
            "entries": [e.to_dict() for e in self.entries],
            "status": self.status,
            "created_at": self.created_at,
            "reconciled_at": self.reconciled_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        entries = [LedgerEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            id=data["id"],
            tx_type=data["tx_type"],
            amount=data["amount"],
            currency=data["currency"],
            stripe_tx_id=data.get("stripe_tx_id"),
            entries=entries,
            status=data["status"],
            created_at=data["created_at"],
            reconciled_at=data.get("reconciled_at"),
        )


class LedgerManager:
    """
    Manages the double-entry ledger for all Stripe transactions.
    
    Principles:
    - Every transaction has balanced debit/credit entries
    - All entries are immutable (corrections via adjustment entries)
    - Full audit trail with timestamps
    - Reconciliation with Stripe Balance Transactions
    """
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.ledger_file = self.data_dir / "stripe_ledger.json"
        self.balances_file = self.data_dir / "account_balances.json"
        
        # Initialize storage
        self._ensure_data_dir()
        self._load_data()
    
    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_data(self) -> None:
        """Load ledger data from files"""
        # Load transactions
        if self.ledger_file.exists():
            try:
                with open(self.ledger_file, 'r') as f:
                    data = json.load(f)
                    self.transactions = {
                        tx_id: Transaction.from_dict(tx_data)
                        for tx_id, tx_data in data.get("transactions", {}).items()
                    }
            except Exception as e:
                logger.error(f"Error loading ledger: {e}")
                self.transactions = {}
        else:
            self.transactions = {}
        
        # Load account balances
        if self.balances_file.exists():
            try:
                with open(self.balances_file, 'r') as f:
                    self.balances = json.load(f)
            except Exception as e:
                logger.error(f"Error loading balances: {e}")
                self.balances = self._default_balances()
        else:
            self.balances = self._default_balances()
    
    def _default_balances(self) -> Dict[str, float]:
        """Default account balances"""
        return {
            AccountType.STRIPE_BALANCE.value: 0.0,
            AccountType.USER_EQUITY.value: 0.0,
            AccountType.TRADING_ACCOUNT.value: 0.0,
            AccountType.FEE_EXPENSE.value: 0.0,
            AccountType.REVENUE.value: 0.0,
            AccountType.PENDING.value: 0.0,
        }
    
    def _save_data(self) -> None:
        """Save ledger data to files"""
        try:
            # Save transactions
            with open(self.ledger_file, 'w') as f:
                json.dump({
                    "transactions": {
                        tx_id: tx.to_dict()
                        for tx_id, tx in self.transactions.items()
                    },
                    "last_updated": datetime.utcnow().isoformat(),
                }, f, indent=2)
            
            # Save balances
            with open(self.balances_file, 'w') as f:
                json.dump({
                    "balances": self.balances,
                    "last_updated": datetime.utcnow().isoformat(),
                }, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving ledger data: {e}")
            raise
    
    def _create_entry(
        self,
        transaction_id: str,
        entry_type: LedgerEntryType,
        account: AccountType,
        debit: float,
        credit: float,
        stripe_tx_id: Optional[str],
        description: str,
        metadata: Dict[str, Any] = None,
    ) -> LedgerEntry:
        """Create a single ledger entry"""
        # Update account balance
        balance_change = debit - credit
        self.balances[account.value] = self.balances.get(account.value, 0.0) + balance_change
        
        return LedgerEntry(
            id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            entry_type=entry_type.value,
            account=account.value,
            debit=debit,
            credit=credit,
            balance_after=self.balances[account.value],
            stripe_tx_id=stripe_tx_id,
            description=description,
            metadata=metadata or {},
            created_at=datetime.utcnow().isoformat(),
        )
    
    def record_deposit(
        self,
        amount: float,
        stripe_tx_id: str,
        currency: str = "eur",
        fee: float = 0.0,
        metadata: Dict[str, Any] = None,
    ) -> Transaction:
        """
        Record a deposit transaction.
        
        Double-entry:
        - Debit: Stripe Balance (asset increases)
        - Credit: User Equity (equity increases)
        - If fee: Debit Fee Expense, Credit Stripe Balance
        """
        tx_id = str(uuid.uuid4())
        entries = []
        
        # Main deposit entry
        entries.append(self._create_entry(
            transaction_id=tx_id,
            entry_type=LedgerEntryType.DEPOSIT,
            account=AccountType.STRIPE_BALANCE,
            debit=amount,
            credit=0.0,
            stripe_tx_id=stripe_tx_id,
            description=f"Deposit of {amount} {currency.upper()}",
            metadata=metadata,
        ))
        
        entries.append(self._create_entry(
            transaction_id=tx_id,
            entry_type=LedgerEntryType.DEPOSIT,
            account=AccountType.USER_EQUITY,
            debit=0.0,
            credit=amount,
            stripe_tx_id=stripe_tx_id,
            description=f"Deposit credited to equity",
            metadata=metadata,
        ))
        
        # Fee entries if applicable
        if fee > 0:
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=LedgerEntryType.FEE,
                account=AccountType.FEE_EXPENSE,
                debit=fee,
                credit=0.0,
                stripe_tx_id=stripe_tx_id,
                description=f"Stripe fee for deposit",
                metadata={"fee_type": "stripe_processing"},
            ))
            
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=LedgerEntryType.FEE,
                account=AccountType.STRIPE_BALANCE,
                debit=0.0,
                credit=fee,
                stripe_tx_id=stripe_tx_id,
                description=f"Fee deducted from balance",
                metadata={"fee_type": "stripe_processing"},
            ))
        
        transaction = Transaction(
            id=tx_id,
            tx_type=LedgerEntryType.DEPOSIT.value,
            amount=amount,
            currency=currency,
            stripe_tx_id=stripe_tx_id,
            entries=entries,
            status="completed",
            created_at=datetime.utcnow().isoformat(),
        )
        
        self.transactions[tx_id] = transaction
        self._save_data()
        
        logger.info(f"Recorded deposit: {amount} {currency}, tx_id={tx_id}")
        return transaction
    
    def record_withdrawal(
        self,
        amount: float,
        stripe_tx_id: str,
        currency: str = "eur",
        fee: float = 0.0,
        metadata: Dict[str, Any] = None,
    ) -> Transaction:
        """
        Record a withdrawal transaction.
        
        Double-entry:
        - Debit: User Equity (equity decreases)
        - Credit: Stripe Balance (asset decreases)
        """
        tx_id = str(uuid.uuid4())
        entries = []
        
        # Main withdrawal entry
        entries.append(self._create_entry(
            transaction_id=tx_id,
            entry_type=LedgerEntryType.WITHDRAWAL,
            account=AccountType.USER_EQUITY,
            debit=amount,
            credit=0.0,
            stripe_tx_id=stripe_tx_id,
            description=f"Withdrawal of {amount} {currency.upper()}",
            metadata=metadata,
        ))
        
        entries.append(self._create_entry(
            transaction_id=tx_id,
            entry_type=LedgerEntryType.WITHDRAWAL,
            account=AccountType.STRIPE_BALANCE,
            debit=0.0,
            credit=amount,
            stripe_tx_id=stripe_tx_id,
            description=f"Withdrawal from Stripe balance",
            metadata=metadata,
        ))
        
        # Fee entries if applicable
        if fee > 0:
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=LedgerEntryType.FEE,
                account=AccountType.FEE_EXPENSE,
                debit=fee,
                credit=0.0,
                stripe_tx_id=stripe_tx_id,
                description=f"Stripe fee for withdrawal",
                metadata={"fee_type": "payout_fee"},
            ))
            
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=LedgerEntryType.FEE,
                account=AccountType.STRIPE_BALANCE,
                debit=0.0,
                credit=fee,
                stripe_tx_id=stripe_tx_id,
                description=f"Fee deducted from balance",
                metadata={"fee_type": "payout_fee"},
            ))
        
        transaction = Transaction(
            id=tx_id,
            tx_type=LedgerEntryType.WITHDRAWAL.value,
            amount=amount,
            currency=currency,
            stripe_tx_id=stripe_tx_id,
            entries=entries,
            status="completed",
            created_at=datetime.utcnow().isoformat(),
        )
        
        self.transactions[tx_id] = transaction
        self._save_data()
        
        logger.info(f"Recorded withdrawal: {amount} {currency}, tx_id={tx_id}")
        return transaction
    
    def record_trade_result(
        self,
        pnl: float,
        trade_id: str,
        currency: str = "eur",
        metadata: Dict[str, Any] = None,
    ) -> Transaction:
        """
        Record trading profit or loss.
        
        Profit (pnl > 0):
        - Debit: Trading Account (asset increases)
        - Credit: Revenue (income increases)
        
        Loss (pnl < 0):
        - Debit: Revenue (expense)
        - Credit: Trading Account (asset decreases)
        """
        tx_id = str(uuid.uuid4())
        entries = []
        
        if pnl >= 0:
            entry_type = LedgerEntryType.TRADE_PROFIT
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=entry_type,
                account=AccountType.TRADING_ACCOUNT,
                debit=pnl,
                credit=0.0,
                stripe_tx_id=None,
                description=f"Trading profit: {pnl} {currency.upper()}",
                metadata={"trade_id": trade_id, **(metadata or {})},
            ))
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=entry_type,
                account=AccountType.REVENUE,
                debit=0.0,
                credit=pnl,
                stripe_tx_id=None,
                description=f"Revenue from trade",
                metadata={"trade_id": trade_id},
            ))
        else:
            entry_type = LedgerEntryType.TRADE_LOSS
            loss = abs(pnl)
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=entry_type,
                account=AccountType.REVENUE,
                debit=loss,
                credit=0.0,
                stripe_tx_id=None,
                description=f"Trading loss: {loss} {currency.upper()}",
                metadata={"trade_id": trade_id, **(metadata or {})},
            ))
            entries.append(self._create_entry(
                transaction_id=tx_id,
                entry_type=entry_type,
                account=AccountType.TRADING_ACCOUNT,
                debit=0.0,
                credit=loss,
                stripe_tx_id=None,
                description=f"Loss deducted from trading account",
                metadata={"trade_id": trade_id},
            ))
        
        transaction = Transaction(
            id=tx_id,
            tx_type=entry_type.value,
            amount=abs(pnl),
            currency=currency,
            stripe_tx_id=None,
            entries=entries,
            status="completed",
            created_at=datetime.utcnow().isoformat(),
        )
        
        self.transactions[tx_id] = transaction
        self._save_data()
        
        logger.info(f"Recorded trade result: {pnl} {currency}, tx_id={tx_id}")
        return transaction
    
    def get_balance(self, account: AccountType) -> float:
        """Get current balance for an account"""
        return self.balances.get(account.value, 0.0)
    
    def get_all_balances(self) -> Dict[str, float]:
        """Get all account balances"""
        return self.balances.copy()
    
    def get_available_balance(self) -> float:
        """Get available balance for trading (Stripe balance minus pending)"""
        return (
            self.balances.get(AccountType.STRIPE_BALANCE.value, 0.0) -
            self.balances.get(AccountType.PENDING.value, 0.0)
        )
    
    def get_total_equity(self) -> float:
        """Get total user equity"""
        return self.balances.get(AccountType.USER_EQUITY.value, 0.0)
    
    def get_transactions(
        self,
        tx_type: Optional[LedgerEntryType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Transaction]:
        """Get transactions with optional filters"""
        transactions = list(self.transactions.values())
        
        if tx_type:
            transactions = [t for t in transactions if t.tx_type == tx_type.value]
        
        if start_date:
            transactions = [
                t for t in transactions
                if datetime.fromisoformat(t.created_at) >= start_date
            ]
        
        if end_date:
            transactions = [
                t for t in transactions
                if datetime.fromisoformat(t.created_at) <= end_date
            ]
        
        # Sort by date descending
        transactions.sort(key=lambda t: t.created_at, reverse=True)
        
        return transactions[:limit]
    
    def get_unreconciled_transactions(self) -> List[Transaction]:
        """Get transactions that haven't been reconciled with Stripe"""
        return [
            t for t in self.transactions.values()
            if t.status != "reconciled" and t.stripe_tx_id
        ]
    
    def mark_reconciled(self, tx_id: str) -> None:
        """Mark a transaction as reconciled"""
        if tx_id in self.transactions:
            self.transactions[tx_id].status = "reconciled"
            self.transactions[tx_id].reconciled_at = datetime.utcnow().isoformat()
            self._save_data()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get ledger summary"""
        return {
            "balances": self.get_all_balances(),
            "available_balance": self.get_available_balance(),
            "total_equity": self.get_total_equity(),
            "total_transactions": len(self.transactions),
            "unreconciled_count": len(self.get_unreconciled_transactions()),
            "last_updated": datetime.utcnow().isoformat(),
        }


# Singleton instance
_ledger_manager: Optional[LedgerManager] = None


def get_ledger_manager(data_dir: str = "/app/data") -> LedgerManager:
    """Get or create the ledger manager singleton"""
    global _ledger_manager
    if _ledger_manager is None:
        _ledger_manager = LedgerManager(data_dir=data_dir)
    return _ledger_manager
