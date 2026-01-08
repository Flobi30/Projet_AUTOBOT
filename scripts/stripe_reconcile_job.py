#!/usr/bin/env python3
"""
AUTOBOT Stripe Reconciliation Job

Nightly job to reconcile internal ledger with Stripe Balance Transactions.
Should be run via cron or scheduler (e.g., daily at 2 AM).

Usage:
    python scripts/stripe_reconcile_job.py [--days N] [--report-only]

Options:
    --days N        Number of days to reconcile (default: 1)
    --report-only   Only generate report, don't mark as reconciled
    --output DIR    Output directory for reports (default: data/reconciliation_reports)
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autobot.stripe.ledger import get_ledger_manager
from autobot.stripe.reconciliation import get_reconciler, ReconciliationStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/reconciliation.log', mode='a'),
    ]
)
logger = logging.getLogger(__name__)


def run_reconciliation(days: int = 1, report_only: bool = False, output_dir: str = None):
    """
    Run the reconciliation job.
    
    Args:
        days: Number of days to reconcile
        report_only: If True, only generate report without marking reconciled
        output_dir: Directory for output reports
    """
    logger.info(f"Starting reconciliation job for last {days} day(s)")
    
    # Initialize components
    data_dir = os.getenv("AUTOBOT_DATA_DIR", "/app/data")
    
    ledger_manager = get_ledger_manager(data_dir=data_dir)
    reconciler = get_reconciler(data_dir=data_dir, ledger_manager=ledger_manager)
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    logger.info(f"Reconciliation period: {start_date.isoformat()} to {end_date.isoformat()}")
    
    # Run reconciliation
    report = reconciler.run_reconciliation(
        start_date=start_date,
        end_date=end_date,
    )
    
    # Log results
    logger.info(f"Reconciliation completed with status: {report.status}")
    logger.info(f"Stripe transactions: {report.stripe_transaction_count}")
    logger.info(f"Ledger transactions: {report.ledger_transaction_count}")
    logger.info(f"Matched: {report.matched_count}")
    logger.info(f"Discrepancies: {report.discrepancy_count}")
    logger.info(f"Total difference: {report.difference} {report.currency.upper()}")
    
    # Handle discrepancies
    if report.discrepancy_count > 0:
        logger.warning(f"Found {report.discrepancy_count} discrepancies!")
        
        for disc in report.discrepancies:
            logger.warning(
                f"  - {disc.discrepancy_type}: {disc.stripe_tx_id} "
                f"(Stripe: {disc.stripe_amount}, Ledger: {disc.ledger_amount})"
            )
        
        # Send alert if configured
        alert_threshold = float(os.getenv("RECONCILIATION_ALERT_THRESHOLD", "10.0"))
        if abs(report.difference) > alert_threshold:
            send_alert(report)
    
    # Save report to output directory
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        report_file = output_path / f"reconciliation_{report.start_date[:10]}_{report.end_date[:10]}.json"
        with open(report_file, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        logger.info(f"Report saved to: {report_file}")
    
    # Return exit code based on status
    if report.status == ReconciliationStatus.FAILED.value:
        return 1
    elif report.status == ReconciliationStatus.COMPLETED_WITH_DISCREPANCIES.value:
        return 2
    else:
        return 0


def send_alert(report):
    """Send alert for significant discrepancies"""
    logger.info("Sending reconciliation alert...")
    
    # Check for webhook URL
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("No alert webhook configured")
        return
    
    try:
        import requests
        
        payload = {
            "text": f"AUTOBOT Reconciliation Alert",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Reconciliation Alert*\n"
                               f"Period: {report.start_date[:10]} to {report.end_date[:10]}\n"
                               f"Discrepancies: {report.discrepancy_count}\n"
                               f"Total Difference: {report.difference} {report.currency.upper()}"
                    }
                }
            ]
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info("Alert sent successfully")
        
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")


def retry_failed_webhooks():
    """Retry any failed webhook events"""
    from autobot.stripe.webhooks import get_webhook_handler
    
    logger.info("Retrying failed webhook events...")
    
    data_dir = os.getenv("AUTOBOT_DATA_DIR", "/app/data")
    webhook_handler = get_webhook_handler(data_dir=data_dir)
    
    result = webhook_handler.retry_failed_events()
    
    logger.info(
        f"Webhook retry results: {result['retried']} retried, "
        f"{result['succeeded']} succeeded, {result['failed']} failed"
    )
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="AUTOBOT Stripe Reconciliation Job"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to reconcile (default: 1)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only generate report, don't mark as reconciled"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for reports"
    )
    parser.add_argument(
        "--retry-webhooks",
        action="store_true",
        help="Also retry failed webhook events"
    )
    
    args = parser.parse_args()
    
    # Ensure log directory exists
    log_dir = Path("/app/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Retry webhooks if requested
        if args.retry_webhooks:
            retry_failed_webhooks()
        
        # Run reconciliation
        exit_code = run_reconciliation(
            days=args.days,
            report_only=args.report_only,
            output_dir=args.output,
        )
        
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Reconciliation job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
