"""
AUTOBOT Stripe Webhooks Module

Robust webhook handling with:
- Signature verification
- Retry mechanism for failed processing
- Event deduplication
- Comprehensive logging
"""

import os
import json
import uuid
import logging
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class WebhookStatus(Enum):
    """Status of webhook processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookEvent:
    """Represents a Stripe webhook event"""
    id: str
    stripe_event_id: str
    event_type: str
    payload: Dict[str, Any]
    status: str
    attempts: int
    last_attempt: Optional[str]
    error_message: Optional[str]
    created_at: str
    processed_at: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebhookEvent':
        return cls(**data)


class WebhookHandler:
    """
    Handles Stripe webhook events with retry mechanism.
    
    Features:
    - Signature verification
    - Event deduplication (idempotency)
    - Automatic retry for failed events
    - Dead letter queue for permanently failed events
    - Comprehensive audit logging
    """
    
    # Events we handle
    SUPPORTED_EVENTS = {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
        "charge.succeeded",
        "charge.failed",
        "charge.refunded",
        "charge.dispute.created",
        "charge.dispute.closed",
        "payout.paid",
        "payout.failed",
        "payout.canceled",
        "checkout.session.completed",
        "checkout.session.expired",
        "customer.created",
        "customer.updated",
        "balance.available",
    }
    
    MAX_RETRY_ATTEMPTS = 5
    RETRY_DELAYS = [60, 300, 900, 3600, 86400]  # 1min, 5min, 15min, 1hr, 24hr
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.events_file = self.data_dir / "webhook_events.json"
        self.dlq_file = self.data_dir / "webhook_dlq.json"  # Dead letter queue
        
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        
        # Event handlers registry
        self._handlers: Dict[str, List[Callable]] = {}
        
        # Load existing events
        self._ensure_data_dir()
        self._load_events()
        
        # Register default handlers
        self._register_default_handlers()
    
    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_events(self) -> None:
        """Load events from storage"""
        if self.events_file.exists():
            try:
                with open(self.events_file, 'r') as f:
                    data = json.load(f)
                    self.events = {
                        event_id: WebhookEvent.from_dict(event_data)
                        for event_id, event_data in data.get("events", {}).items()
                    }
            except Exception as e:
                logger.error(f"Error loading webhook events: {e}")
                self.events = {}
        else:
            self.events = {}
        
        # Load dead letter queue
        if self.dlq_file.exists():
            try:
                with open(self.dlq_file, 'r') as f:
                    data = json.load(f)
                    self.dlq = {
                        event_id: WebhookEvent.from_dict(event_data)
                        for event_id, event_data in data.get("events", {}).items()
                    }
            except Exception as e:
                logger.error(f"Error loading DLQ: {e}")
                self.dlq = {}
        else:
            self.dlq = {}
    
    def _save_events(self) -> None:
        """Save events to storage"""
        try:
            with open(self.events_file, 'w') as f:
                json.dump({
                    "events": {
                        event_id: event.to_dict()
                        for event_id, event in self.events.items()
                    },
                    "last_updated": datetime.utcnow().isoformat(),
                }, f, indent=2)
            
            with open(self.dlq_file, 'w') as f:
                json.dump({
                    "events": {
                        event_id: event.to_dict()
                        for event_id, event in self.dlq.items()
                    },
                    "last_updated": datetime.utcnow().isoformat(),
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving webhook events: {e}")
    
    def _register_default_handlers(self) -> None:
        """Register default event handlers"""
        # These will be connected to the ledger
        pass
    
    def register_handler(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.info(f"Registered handler for {event_type}")
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature"""
        if not self.webhook_secret:
            logger.warning("Webhook secret not configured, skipping verification")
            return True
        
        try:
            # Parse signature header
            elements = dict(item.split("=") for item in signature.split(","))
            timestamp = elements.get("t")
            v1_signature = elements.get("v1")
            
            if not timestamp or not v1_signature:
                logger.error("Invalid signature format")
                return False
            
            # Check timestamp (prevent replay attacks)
            event_time = datetime.fromtimestamp(int(timestamp))
            if datetime.utcnow() - event_time > timedelta(minutes=5):
                logger.error("Webhook timestamp too old")
                return False
            
            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            expected_sig = hmac.new(
                self.webhook_secret.encode('utf-8'),
                signed_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            return hmac.compare_digest(expected_sig, v1_signature)
            
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    def is_duplicate(self, stripe_event_id: str) -> bool:
        """Check if event has already been processed (idempotency)"""
        for event in self.events.values():
            if event.stripe_event_id == stripe_event_id:
                if event.status == WebhookStatus.COMPLETED.value:
                    return True
        return False
    
    def receive_event(
        self,
        payload: bytes,
        signature: str,
    ) -> Dict[str, Any]:
        """
        Receive and process a webhook event.
        
        Returns:
            Dict with status and event_id
        """
        # Verify signature
        if not self.verify_signature(payload, signature):
            logger.error("Invalid webhook signature")
            return {"status": "error", "message": "Invalid signature"}
        
        # Parse payload
        try:
            event_data = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            return {"status": "error", "message": "Invalid JSON"}
        
        stripe_event_id = event_data.get("id")
        event_type = event_data.get("type")
        
        # Check for duplicate
        if self.is_duplicate(stripe_event_id):
            logger.info(f"Duplicate event ignored: {stripe_event_id}")
            return {"status": "duplicate", "event_id": stripe_event_id}
        
        # Check if event type is supported
        if event_type not in self.SUPPORTED_EVENTS:
            logger.info(f"Unsupported event type: {event_type}")
            return {"status": "ignored", "event_type": event_type}
        
        # Create event record
        event = WebhookEvent(
            id=str(uuid.uuid4()),
            stripe_event_id=stripe_event_id,
            event_type=event_type,
            payload=event_data,
            status=WebhookStatus.PENDING.value,
            attempts=0,
            last_attempt=None,
            error_message=None,
            created_at=datetime.utcnow().isoformat(),
            processed_at=None,
        )
        
        self.events[event.id] = event
        self._save_events()
        
        # Process event
        result = self.process_event(event.id)
        
        return {
            "status": "received",
            "event_id": event.id,
            "processing_result": result,
        }
    
    def process_event(self, event_id: str) -> Dict[str, Any]:
        """Process a single webhook event"""
        if event_id not in self.events:
            return {"status": "error", "message": "Event not found"}
        
        event = self.events[event_id]
        event.status = WebhookStatus.PROCESSING.value
        event.attempts += 1
        event.last_attempt = datetime.utcnow().isoformat()
        
        try:
            # Get handlers for this event type
            handlers = self._handlers.get(event.event_type, [])
            
            if not handlers:
                logger.warning(f"No handlers for event type: {event.event_type}")
            
            # Execute all handlers
            for handler in handlers:
                handler(event.payload)
            
            # Mark as completed
            event.status = WebhookStatus.COMPLETED.value
            event.processed_at = datetime.utcnow().isoformat()
            event.error_message = None
            
            logger.info(f"Successfully processed event: {event.stripe_event_id}")
            
            self._save_events()
            return {"status": "success", "event_id": event_id}
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing event {event_id}: {error_msg}")
            
            event.error_message = error_msg
            
            # Check if we should retry or move to DLQ
            if event.attempts >= self.MAX_RETRY_ATTEMPTS:
                event.status = WebhookStatus.FAILED.value
                # Move to dead letter queue
                self.dlq[event_id] = event
                del self.events[event_id]
                logger.error(f"Event {event_id} moved to DLQ after {event.attempts} attempts")
            else:
                event.status = WebhookStatus.RETRYING.value
            
            self._save_events()
            return {"status": "error", "message": error_msg, "attempts": event.attempts}
    
    def retry_failed_events(self) -> Dict[str, Any]:
        """Retry all events in retrying status"""
        retried = 0
        succeeded = 0
        failed = 0
        
        for event_id, event in list(self.events.items()):
            if event.status == WebhookStatus.RETRYING.value:
                # Check if enough time has passed since last attempt
                if event.last_attempt:
                    last_attempt = datetime.fromisoformat(event.last_attempt)
                    delay_index = min(event.attempts - 1, len(self.RETRY_DELAYS) - 1)
                    required_delay = timedelta(seconds=self.RETRY_DELAYS[delay_index])
                    
                    if datetime.utcnow() - last_attempt < required_delay:
                        continue
                
                retried += 1
                result = self.process_event(event_id)
                
                if result.get("status") == "success":
                    succeeded += 1
                else:
                    failed += 1
        
        return {
            "retried": retried,
            "succeeded": succeeded,
            "failed": failed,
        }
    
    def get_event(self, event_id: str) -> Optional[WebhookEvent]:
        """Get a specific event"""
        return self.events.get(event_id) or self.dlq.get(event_id)
    
    def get_pending_events(self) -> List[WebhookEvent]:
        """Get all pending events"""
        return [e for e in self.events.values() if e.status == WebhookStatus.PENDING.value]
    
    def get_failed_events(self) -> List[WebhookEvent]:
        """Get all failed events (in DLQ)"""
        return list(self.dlq.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get webhook processing statistics"""
        status_counts = {}
        for event in self.events.values():
            status_counts[event.status] = status_counts.get(event.status, 0) + 1
        
        return {
            "total_events": len(self.events),
            "dlq_count": len(self.dlq),
            "status_counts": status_counts,
            "last_updated": datetime.utcnow().isoformat(),
        }
    
    def reprocess_dlq_event(self, event_id: str) -> Dict[str, Any]:
        """Manually reprocess an event from the DLQ"""
        if event_id not in self.dlq:
            return {"status": "error", "message": "Event not in DLQ"}
        
        # Move back to events
        event = self.dlq[event_id]
        event.status = WebhookStatus.PENDING.value
        event.attempts = 0
        self.events[event_id] = event
        del self.dlq[event_id]
        
        # Process
        result = self.process_event(event_id)
        return result


# Singleton instance
_webhook_handler: Optional[WebhookHandler] = None


def get_webhook_handler(data_dir: str = "/app/data") -> WebhookHandler:
    """Get or create the webhook handler singleton"""
    global _webhook_handler
    if _webhook_handler is None:
        _webhook_handler = WebhookHandler(data_dir=data_dir)
    return _webhook_handler
