"""
AUTOBOT Stripe API Routes

FastAPI router for Stripe ledger, webhooks, and reconciliation endpoints.
"""

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime, timedelta
import os
import logging

from autobot.stripe.ledger import get_ledger_manager, TransactionType
from autobot.stripe.webhooks import get_webhook_handler
from autobot.stripe.reconciliation import get_reconciler

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["stripe"])

# Data directory
DATA_DIR = os.getenv("AUTOBOT_DATA_DIR", "/app/data")


# ============================================================================
# Webhook Endpoints
# ============================================================================

@router.post("/webhook/receive")
async def receive_webhook(request: Request):
    """
    Receive and process Stripe webhook events.
    
    This endpoint verifies the webhook signature and processes the event
    using the WebhookHandler with retry mechanism.
    """
    try:
        payload = await request.body()
        signature = request.headers.get("stripe-signature", "")
        
        if not signature:
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")
        
        webhook_handler = get_webhook_handler(data_dir=DATA_DIR)
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        
        # Register ledger handlers if not already registered
        _register_ledger_handlers(webhook_handler, ledger_manager)
        
        # Receive and process the event
        event = webhook_handler.receive_event(
            payload=payload.decode("utf-8"),
            signature=signature,
        )
        
        if event is None:
            # Duplicate event, already processed
            return JSONResponse({"status": "duplicate", "message": "Event already processed"})
        
        # Process the event
        success = webhook_handler.process_event(event.event_id)
        
        if success:
            return JSONResponse({"status": "success", "event_id": event.event_id})
        else:
            return JSONResponse(
                {"status": "queued", "event_id": event.event_id, "message": "Event queued for retry"},
                status_code=202
            )
            
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/pending")
async def get_pending_webhooks():
    """Get all pending webhook events"""
    try:
        webhook_handler = get_webhook_handler(data_dir=DATA_DIR)
        events = webhook_handler.get_pending_events()
        
        return JSONResponse({
            "count": len(events),
            "events": [e.to_dict() for e in events]
        })
    except Exception as e:
        logger.error(f"Error getting pending webhooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/failed")
async def get_failed_webhooks():
    """Get all failed webhook events (dead letter queue)"""
    try:
        webhook_handler = get_webhook_handler(data_dir=DATA_DIR)
        events = webhook_handler.get_failed_events()
        
        return JSONResponse({
            "count": len(events),
            "events": [e.to_dict() for e in events]
        })
    except Exception as e:
        logger.error(f"Error getting failed webhooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/retry")
async def retry_failed_webhooks():
    """Retry all failed webhook events"""
    try:
        webhook_handler = get_webhook_handler(data_dir=DATA_DIR)
        result = webhook_handler.retry_failed_events()
        
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Error retrying webhooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/reprocess/{event_id}")
async def reprocess_dlq_event(event_id: str):
    """Manually reprocess a specific event from the dead letter queue"""
    try:
        webhook_handler = get_webhook_handler(data_dir=DATA_DIR)
        success = webhook_handler.reprocess_dlq_event(event_id)
        
        if success:
            return JSONResponse({"status": "success", "event_id": event_id})
        else:
            return JSONResponse(
                {"status": "failed", "event_id": event_id},
                status_code=400
            )
    except Exception as e:
        logger.error(f"Error reprocessing event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Ledger Endpoints
# ============================================================================

@router.get("/ledger/summary")
async def get_ledger_summary():
    """Get ledger summary with account balances"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        summary = ledger_manager.get_summary()
        
        return JSONResponse(summary)
    except Exception as e:
        logger.error(f"Error getting ledger summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ledger/transactions")
async def get_ledger_transactions(
    tx_type: Optional[str] = Query(None, description="Transaction type filter"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(100, description="Maximum number of transactions to return"),
):
    """Get ledger transactions with optional filters"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        
        # Parse transaction type
        transaction_type = None
        if tx_type:
            try:
                transaction_type = TransactionType(tx_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid transaction type: {tx_type}")
        
        # Parse dates
        start = None
        end = None
        if start_date:
            start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if end_date:
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        
        transactions = ledger_manager.get_transactions(
            tx_type=transaction_type,
            start_date=start,
            end_date=end,
            limit=limit,
        )
        
        return JSONResponse({
            "count": len(transactions),
            "transactions": [t.to_dict() for t in transactions]
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ledger/balance")
async def get_ledger_balance():
    """Get available balance for trading"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        
        available = ledger_manager.get_available_balance()
        summary = ledger_manager.get_summary()
        
        return JSONResponse({
            "available_balance": available,
            "account_balances": summary.get("account_balances", {}),
            "currency": "EUR"
        })
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ledger/unreconciled")
async def get_unreconciled_transactions():
    """Get transactions not yet reconciled with Stripe"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        transactions = ledger_manager.get_unreconciled_transactions()
        
        return JSONResponse({
            "count": len(transactions),
            "transactions": [t.to_dict() for t in transactions]
        })
    except Exception as e:
        logger.error(f"Error getting unreconciled transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Reconciliation Endpoints
# ============================================================================

@router.get("/reconciliation/latest")
async def get_latest_reconciliation():
    """Get the latest reconciliation report"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        reconciler = get_reconciler(data_dir=DATA_DIR, ledger_manager=ledger_manager)
        
        report = reconciler.get_latest_report()
        
        if report is None:
            return JSONResponse({"status": "no_reports", "message": "No reconciliation reports found"})
        
        return JSONResponse(report.to_dict())
    except Exception as e:
        logger.error(f"Error getting latest reconciliation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/report/{report_id}")
async def get_reconciliation_report(report_id: str):
    """Get a specific reconciliation report by ID"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        reconciler = get_reconciler(data_dir=DATA_DIR, ledger_manager=ledger_manager)
        
        report = reconciler.get_report(report_id)
        
        if report is None:
            raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        
        return JSONResponse(report.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reconciliation/run")
async def run_reconciliation(
    days: int = Query(1, description="Number of days to reconcile"),
):
    """Trigger a reconciliation run"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        reconciler = get_reconciler(data_dir=DATA_DIR, ledger_manager=ledger_manager)
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        report = reconciler.run_reconciliation(
            start_date=start_date,
            end_date=end_date,
        )
        
        return JSONResponse(report.to_dict())
    except Exception as e:
        logger.error(f"Error running reconciliation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/discrepancies")
async def get_unresolved_discrepancies():
    """Get all unresolved discrepancies across all reports"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        reconciler = get_reconciler(data_dir=DATA_DIR, ledger_manager=ledger_manager)
        
        discrepancies = reconciler.get_unresolved_discrepancies()
        
        return JSONResponse({
            "count": len(discrepancies),
            "discrepancies": discrepancies
        })
    except Exception as e:
        logger.error(f"Error getting discrepancies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reconciliation/resolve/{report_id}/{discrepancy_id}")
async def resolve_discrepancy(
    report_id: str,
    discrepancy_id: str,
    request: Request,
):
    """Mark a discrepancy as resolved"""
    try:
        body = await request.json()
        resolution_notes = body.get("resolution_notes", "")
        
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        reconciler = get_reconciler(data_dir=DATA_DIR, ledger_manager=ledger_manager)
        
        success = reconciler.resolve_discrepancy(
            report_id=report_id,
            discrepancy_id=discrepancy_id,
            resolution_notes=resolution_notes,
        )
        
        if success:
            return JSONResponse({"status": "resolved", "discrepancy_id": discrepancy_id})
        else:
            raise HTTPException(status_code=404, detail="Discrepancy not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving discrepancy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/summary")
async def get_reconciliation_summary():
    """Get reconciliation summary statistics"""
    try:
        ledger_manager = get_ledger_manager(data_dir=DATA_DIR)
        reconciler = get_reconciler(data_dir=DATA_DIR, ledger_manager=ledger_manager)
        
        summary = reconciler.get_summary()
        
        return JSONResponse(summary)
    except Exception as e:
        logger.error(f"Error getting reconciliation summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Helper Functions
# ============================================================================

def _register_ledger_handlers(webhook_handler, ledger_manager):
    """Register webhook handlers that update the ledger"""
    
    def handle_payment_succeeded(event_data: dict) -> bool:
        """Handle successful payment - record deposit in ledger"""
        try:
            payment_intent = event_data.get("object", {})
            amount = payment_intent.get("amount", 0) / 100  # Convert from cents
            currency = payment_intent.get("currency", "eur")
            stripe_tx_id = payment_intent.get("id", "")
            
            # Get fee from charges if available
            fee = 0.0
            charges = payment_intent.get("charges", {}).get("data", [])
            if charges:
                balance_tx = charges[0].get("balance_transaction")
                if isinstance(balance_tx, dict):
                    fee = balance_tx.get("fee", 0) / 100
            
            ledger_manager.record_deposit(
                amount=amount,
                stripe_tx_id=stripe_tx_id,
                currency=currency,
                fee=fee,
                metadata={"source": "webhook", "event_type": "payment_intent.succeeded"}
            )
            
            logger.info(f"Recorded deposit from webhook: {amount} {currency}")
            return True
            
        except Exception as e:
            logger.error(f"Error handling payment_intent.succeeded: {e}")
            return False
    
    def handle_payout_paid(event_data: dict) -> bool:
        """Handle successful payout - record withdrawal in ledger"""
        try:
            payout = event_data.get("object", {})
            amount = payout.get("amount", 0) / 100  # Convert from cents
            currency = payout.get("currency", "eur")
            stripe_tx_id = payout.get("id", "")
            
            ledger_manager.record_withdrawal(
                amount=amount,
                stripe_tx_id=stripe_tx_id,
                currency=currency,
                fee=0.0,  # Payout fees handled separately
                metadata={"source": "webhook", "event_type": "payout.paid"}
            )
            
            logger.info(f"Recorded withdrawal from webhook: {amount} {currency}")
            return True
            
        except Exception as e:
            logger.error(f"Error handling payout.paid: {e}")
            return False
    
    def handle_checkout_completed(event_data: dict) -> bool:
        """Handle checkout session completed"""
        try:
            session = event_data.get("object", {})
            amount = session.get("amount_total", 0) / 100
            currency = session.get("currency", "eur")
            stripe_tx_id = session.get("payment_intent", session.get("id", ""))
            
            ledger_manager.record_deposit(
                amount=amount,
                stripe_tx_id=stripe_tx_id,
                currency=currency,
                fee=0.0,  # Fee calculated separately
                metadata={"source": "webhook", "event_type": "checkout.session.completed"}
            )
            
            logger.info(f"Recorded checkout deposit from webhook: {amount} {currency}")
            return True
            
        except Exception as e:
            logger.error(f"Error handling checkout.session.completed: {e}")
            return False
    
    # Register handlers
    webhook_handler.register_handler("payment_intent.succeeded", handle_payment_succeeded)
    webhook_handler.register_handler("payout.paid", handle_payout_paid)
    webhook_handler.register_handler("checkout.session.completed", handle_checkout_completed)
