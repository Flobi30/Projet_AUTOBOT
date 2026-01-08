"""
AUTOBOT Stripe Reconciliation Module

Nightly reconciliation of internal ledger with Stripe Balance Transactions.
Generates reports and alerts for discrepancies.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import stripe
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None
    STRIPE_AVAILABLE = False


class ReconciliationStatus(Enum):
    """Status of reconciliation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_DISCREPANCIES = "completed_with_discrepancies"
    FAILED = "failed"


@dataclass
class Discrepancy:
    """Represents a discrepancy between ledger and Stripe"""
    id: str
    stripe_tx_id: str
    ledger_tx_id: Optional[str]
    discrepancy_type: str  # missing_in_ledger, missing_in_stripe, amount_mismatch
    stripe_amount: float
    ledger_amount: float
    difference: float
    currency: str
    description: str
    created_at: str
    resolved: bool = False
    resolution_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Discrepancy':
        return cls(**data)


@dataclass
class ReconciliationReport:
    """Report from a reconciliation run"""
    id: str
    start_date: str
    end_date: str
    status: str
    stripe_transaction_count: int
    ledger_transaction_count: int
    matched_count: int
    discrepancy_count: int
    discrepancies: List[Discrepancy]
    stripe_total: float
    ledger_total: float
    difference: float
    currency: str
    created_at: str
    completed_at: Optional[str]
    error_message: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **{k: v for k, v in asdict(self).items() if k != 'discrepancies'},
            'discrepancies': [d.to_dict() for d in self.discrepancies],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReconciliationReport':
        discrepancies = [Discrepancy.from_dict(d) for d in data.get('discrepancies', [])]
        return cls(
            id=data['id'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            status=data['status'],
            stripe_transaction_count=data['stripe_transaction_count'],
            ledger_transaction_count=data['ledger_transaction_count'],
            matched_count=data['matched_count'],
            discrepancy_count=data['discrepancy_count'],
            discrepancies=discrepancies,
            stripe_total=data['stripe_total'],
            ledger_total=data['ledger_total'],
            difference=data['difference'],
            currency=data['currency'],
            created_at=data['created_at'],
            completed_at=data.get('completed_at'),
            error_message=data.get('error_message'),
        )


class StripeReconciler:
    """
    Reconciles internal ledger with Stripe Balance Transactions.
    
    Features:
    - Fetches Stripe Balance Transactions for date range
    - Compares with internal ledger entries
    - Identifies discrepancies (missing, amount mismatch)
    - Generates detailed reports
    - Supports manual resolution of discrepancies
    """
    
    TOLERANCE = 0.01  # Allow 1 cent tolerance for rounding
    
    def __init__(self, data_dir: str = "/app/data", ledger_manager=None):
        self.data_dir = Path(data_dir)
        self.reports_dir = self.data_dir / "reconciliation_reports"
        self.reports_file = self.data_dir / "reconciliation_history.json"
        
        self.ledger_manager = ledger_manager
        
        # Initialize Stripe
        if STRIPE_AVAILABLE:
            stripe.api_key = os.getenv("STRIPE_API_KEY")
        
        # Load existing reports
        self._ensure_dirs()
        self._load_reports()
    
    def _ensure_dirs(self) -> None:
        """Ensure directories exist"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_reports(self) -> None:
        """Load reconciliation history"""
        if self.reports_file.exists():
            try:
                with open(self.reports_file, 'r') as f:
                    data = json.load(f)
                    self.reports = {
                        report_id: ReconciliationReport.from_dict(report_data)
                        for report_id, report_data in data.get("reports", {}).items()
                    }
            except Exception as e:
                logger.error(f"Error loading reconciliation reports: {e}")
                self.reports = {}
        else:
            self.reports = {}
    
    def _save_reports(self) -> None:
        """Save reconciliation history"""
        try:
            with open(self.reports_file, 'w') as f:
                json.dump({
                    "reports": {
                        report_id: report.to_dict()
                        for report_id, report in self.reports.items()
                    },
                    "last_updated": datetime.utcnow().isoformat(),
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reconciliation reports: {e}")
    
    def _save_report_file(self, report: ReconciliationReport) -> str:
        """Save individual report to file"""
        filename = f"reconciliation_{report.start_date}_{report.end_date}.json"
        filepath = self.reports_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        return str(filepath)
    
    def fetch_stripe_transactions(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch Balance Transactions from Stripe"""
        if not STRIPE_AVAILABLE:
            logger.error("Stripe library not available")
            return []
        
        if not stripe.api_key:
            logger.error("Stripe API key not configured")
            return []
        
        try:
            transactions = []
            has_more = True
            starting_after = None
            
            while has_more and len(transactions) < limit:
                params = {
                    "created": {
                        "gte": int(start_date.timestamp()),
                        "lte": int(end_date.timestamp()),
                    },
                    "limit": min(100, limit - len(transactions)),
                }
                
                if starting_after:
                    params["starting_after"] = starting_after
                
                response = stripe.BalanceTransaction.list(**params)
                
                for tx in response.data:
                    transactions.append({
                        "id": tx.id,
                        "amount": tx.amount / 100,  # Convert from cents
                        "fee": tx.fee / 100,
                        "net": tx.net / 100,
                        "currency": tx.currency,
                        "type": tx.type,
                        "description": tx.description,
                        "source": tx.source,
                        "created": datetime.fromtimestamp(tx.created).isoformat(),
                    })
                
                has_more = response.has_more
                if response.data:
                    starting_after = response.data[-1].id
            
            logger.info(f"Fetched {len(transactions)} Stripe transactions")
            return transactions
            
        except Exception as e:
            logger.error(f"Error fetching Stripe transactions: {e}")
            return []
    
    def run_reconciliation(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ReconciliationReport:
        """
        Run reconciliation for a date range.
        
        Default: Previous 24 hours
        """
        import uuid
        
        # Default to last 24 hours
        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=1)
        
        report_id = str(uuid.uuid4())
        
        report = ReconciliationReport(
            id=report_id,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            status=ReconciliationStatus.IN_PROGRESS.value,
            stripe_transaction_count=0,
            ledger_transaction_count=0,
            matched_count=0,
            discrepancy_count=0,
            discrepancies=[],
            stripe_total=0.0,
            ledger_total=0.0,
            difference=0.0,
            currency="eur",
            created_at=datetime.utcnow().isoformat(),
            completed_at=None,
            error_message=None,
        )
        
        try:
            # Fetch Stripe transactions
            stripe_txs = self.fetch_stripe_transactions(start_date, end_date)
            report.stripe_transaction_count = len(stripe_txs)
            
            # Get ledger transactions
            ledger_txs = []
            if self.ledger_manager:
                ledger_txs = self.ledger_manager.get_transactions(
                    start_date=start_date,
                    end_date=end_date,
                    limit=1000,
                )
            report.ledger_transaction_count = len(ledger_txs)
            
            # Build lookup maps
            stripe_by_id = {tx["id"]: tx for tx in stripe_txs}
            ledger_by_stripe_id = {
                tx.stripe_tx_id: tx for tx in ledger_txs if tx.stripe_tx_id
            }
            
            # Calculate totals
            report.stripe_total = sum(tx["net"] for tx in stripe_txs)
            report.ledger_total = sum(tx.amount for tx in ledger_txs)
            
            discrepancies = []
            matched = 0
            
            # Check each Stripe transaction
            for stripe_id, stripe_tx in stripe_by_id.items():
                if stripe_id in ledger_by_stripe_id:
                    ledger_tx = ledger_by_stripe_id[stripe_id]
                    
                    # Check amount match
                    diff = abs(stripe_tx["net"] - ledger_tx.amount)
                    if diff > self.TOLERANCE:
                        discrepancies.append(Discrepancy(
                            id=str(uuid.uuid4()),
                            stripe_tx_id=stripe_id,
                            ledger_tx_id=ledger_tx.id,
                            discrepancy_type="amount_mismatch",
                            stripe_amount=stripe_tx["net"],
                            ledger_amount=ledger_tx.amount,
                            difference=stripe_tx["net"] - ledger_tx.amount,
                            currency=stripe_tx["currency"],
                            description=f"Amount mismatch: Stripe={stripe_tx['net']}, Ledger={ledger_tx.amount}",
                            created_at=datetime.utcnow().isoformat(),
                        ))
                    else:
                        matched += 1
                        # Mark as reconciled in ledger
                        if self.ledger_manager:
                            self.ledger_manager.mark_reconciled(ledger_tx.id)
                else:
                    # Missing in ledger
                    discrepancies.append(Discrepancy(
                        id=str(uuid.uuid4()),
                        stripe_tx_id=stripe_id,
                        ledger_tx_id=None,
                        discrepancy_type="missing_in_ledger",
                        stripe_amount=stripe_tx["net"],
                        ledger_amount=0.0,
                        difference=stripe_tx["net"],
                        currency=stripe_tx["currency"],
                        description=f"Transaction {stripe_id} exists in Stripe but not in ledger",
                        created_at=datetime.utcnow().isoformat(),
                    ))
            
            # Check for ledger entries missing in Stripe
            for ledger_tx in ledger_txs:
                if ledger_tx.stripe_tx_id and ledger_tx.stripe_tx_id not in stripe_by_id:
                    discrepancies.append(Discrepancy(
                        id=str(uuid.uuid4()),
                        stripe_tx_id=ledger_tx.stripe_tx_id,
                        ledger_tx_id=ledger_tx.id,
                        discrepancy_type="missing_in_stripe",
                        stripe_amount=0.0,
                        ledger_amount=ledger_tx.amount,
                        difference=-ledger_tx.amount,
                        currency=ledger_tx.currency,
                        description=f"Transaction {ledger_tx.id} exists in ledger but not in Stripe",
                        created_at=datetime.utcnow().isoformat(),
                    ))
            
            # Update report
            report.matched_count = matched
            report.discrepancy_count = len(discrepancies)
            report.discrepancies = discrepancies
            report.difference = report.stripe_total - report.ledger_total
            
            if discrepancies:
                report.status = ReconciliationStatus.COMPLETED_WITH_DISCREPANCIES.value
            else:
                report.status = ReconciliationStatus.COMPLETED.value
            
            report.completed_at = datetime.utcnow().isoformat()
            
            logger.info(
                f"Reconciliation completed: {matched} matched, "
                f"{len(discrepancies)} discrepancies, "
                f"difference={report.difference}"
            )
            
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            report.status = ReconciliationStatus.FAILED.value
            report.error_message = str(e)
        
        # Save report
        self.reports[report_id] = report
        self._save_reports()
        self._save_report_file(report)
        
        return report
    
    def get_report(self, report_id: str) -> Optional[ReconciliationReport]:
        """Get a specific report"""
        return self.reports.get(report_id)
    
    def get_latest_report(self) -> Optional[ReconciliationReport]:
        """Get the most recent report"""
        if not self.reports:
            return None
        
        sorted_reports = sorted(
            self.reports.values(),
            key=lambda r: r.created_at,
            reverse=True
        )
        return sorted_reports[0] if sorted_reports else None
    
    def get_unresolved_discrepancies(self) -> List[Discrepancy]:
        """Get all unresolved discrepancies across all reports"""
        unresolved = []
        for report in self.reports.values():
            for disc in report.discrepancies:
                if not disc.resolved:
                    unresolved.append(disc)
        return unresolved
    
    def resolve_discrepancy(
        self,
        report_id: str,
        discrepancy_id: str,
        resolution_notes: str,
    ) -> bool:
        """Mark a discrepancy as resolved"""
        if report_id not in self.reports:
            return False
        
        report = self.reports[report_id]
        for disc in report.discrepancies:
            if disc.id == discrepancy_id:
                disc.resolved = True
                disc.resolution_notes = resolution_notes
                self._save_reports()
                return True
        
        return False
    
    def get_summary(self) -> Dict[str, Any]:
        """Get reconciliation summary"""
        total_reports = len(self.reports)
        unresolved = self.get_unresolved_discrepancies()
        latest = self.get_latest_report()
        
        return {
            "total_reports": total_reports,
            "unresolved_discrepancies": len(unresolved),
            "latest_report": latest.to_dict() if latest else None,
            "last_reconciliation": latest.created_at if latest else None,
        }


# Singleton instance
_reconciler: Optional[StripeReconciler] = None


def get_reconciler(data_dir: str = "/app/data", ledger_manager=None) -> StripeReconciler:
    """Get or create the reconciler singleton"""
    global _reconciler
    if _reconciler is None:
        _reconciler = StripeReconciler(data_dir=data_dir, ledger_manager=ledger_manager)
    return _reconciler
