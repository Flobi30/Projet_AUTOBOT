"""
Multi-signature transaction verification system for AUTOBOT.

This module provides a robust multi-signature verification system for
high-value transactions, enhancing security and preventing unauthorized
or fraudulent trading activities.
"""

import time
import logging
import threading
import hashlib
import hmac
import base64
import json
import os
import secrets
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)

class MultiSignatureVerifier:
    """
    Multi-signature verification system for high-value transactions.
    
    This class provides a robust verification system that requires multiple
    signatures for high-value transactions, enhancing security and preventing
    unauthorized or fraudulent trading activities.
    """
    
    def __init__(
        self,
        threshold_amount: float = 1000.0,
        required_signatures: int = 2,
        signature_timeout: float = 300.0,
        verification_keys: Optional[List[str]] = None,
        auto_verify_small_transactions: bool = True,
        visible_interface: bool = True
    ):
        """
        Initialize the multi-signature verifier.
        
        Args:
            threshold_amount: Amount threshold for requiring multi-signature
            required_signatures: Number of signatures required for verification
            signature_timeout: Timeout in seconds for collecting signatures
            verification_keys: List of verification keys for signatures
            auto_verify_small_transactions: Whether to auto-verify small transactions
            visible_interface: Whether to show verification messages in the interface
        """
        self.threshold_amount = threshold_amount
        self.required_signatures = required_signatures
        self.signature_timeout = signature_timeout
        self.auto_verify_small_transactions = auto_verify_small_transactions
        self.visible_interface = visible_interface
        
        self._pending_transactions = {}
        self._verified_transactions = {}
        self._rejected_transactions = {}
        self._verification_keys = verification_keys or []
        self._lock = threading.Lock()
        
        if not self._verification_keys:
            self._generate_verification_keys()
    
    def _generate_verification_keys(self, num_keys: int = 3) -> None:
        """
        Generate verification keys.
        
        Args:
            num_keys: Number of verification keys to generate
        """
        self._verification_keys = [
            base64.b64encode(secrets.token_bytes(32)).decode('utf-8')
            for _ in range(num_keys)
        ]
        
        if self.visible_interface:
            logger.info(f"Generated {num_keys} verification keys")
        else:
            logger.debug(f"Generated {num_keys} verification keys")
    
    def get_verification_keys(self) -> List[str]:
        """
        Get verification keys.
        
        Returns:
            List: Verification keys
        """
        return self._verification_keys.copy()
    
    def add_verification_key(self, key: str) -> None:
        """
        Add a verification key.
        
        Args:
            key: Verification key to add
        """
        with self._lock:
            if key not in self._verification_keys:
                self._verification_keys.append(key)
                
                if self.visible_interface:
                    logger.info("Added verification key")
                else:
                    logger.debug("Added verification key")
    
    def remove_verification_key(self, key: str) -> bool:
        """
        Remove a verification key.
        
        Args:
            key: Verification key to remove
            
        Returns:
            bool: Whether the key was removed
        """
        with self._lock:
            if key in self._verification_keys:
                self._verification_keys.remove(key)
                
                if self.visible_interface:
                    logger.info("Removed verification key")
                else:
                    logger.debug("Removed verification key")
                
                return True
            
            return False
    
    def create_transaction(
        self,
        transaction_data: Dict[str, Any],
        transaction_id: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Create a transaction for verification.
        
        Args:
            transaction_data: Transaction data
            transaction_id: Optional transaction ID
            
        Returns:
            Tuple: Transaction ID and transaction data
        """
        with self._lock:
            if transaction_id is None:
                transaction_id = self._generate_transaction_id(transaction_data)
            
            if transaction_id in self._pending_transactions:
                return transaction_id, self._pending_transactions[transaction_id]
            
            transaction = {
                "id": transaction_id,
                "data": transaction_data,
                "amount": transaction_data.get("amount", 0.0),
                "created_at": time.time(),
                "expires_at": time.time() + self.signature_timeout,
                "signatures": {},
                "status": "pending"
            }
            
            if (self.auto_verify_small_transactions and
                transaction["amount"] < self.threshold_amount):
                transaction["status"] = "verified"
                transaction["verified_at"] = time.time()
                self._verified_transactions[transaction_id] = transaction
                
                if self.visible_interface:
                    logger.info(f"Auto-verified small transaction: {transaction_id}")
                else:
                    logger.debug(f"Auto-verified small transaction: {transaction_id}")
            else:
                self._pending_transactions[transaction_id] = transaction
                
                if self.visible_interface:
                    logger.info(f"Created transaction for verification: {transaction_id}")
                else:
                    logger.debug(f"Created transaction for verification: {transaction_id}")
            
            return transaction_id, transaction
    
    def _generate_transaction_id(self, transaction_data: Dict[str, Any]) -> str:
        """
        Generate a transaction ID.
        
        Args:
            transaction_data: Transaction data
            
        Returns:
            str: Transaction ID
        """
        data_str = json.dumps(transaction_data, sort_keys=True)
        timestamp = str(int(time.time() * 1000))
        
        hash_input = f"{data_str}:{timestamp}"
        transaction_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        return f"tx_{transaction_hash[:16]}"
    
    def sign_transaction(
        self,
        transaction_id: str,
        key_index: int,
        signature: Optional[str] = None
    ) -> bool:
        """
        Sign a transaction.
        
        Args:
            transaction_id: Transaction ID
            key_index: Index of the verification key to use
            signature: Optional signature (if None, will be generated)
            
        Returns:
            bool: Whether the signature was added
        """
        with self._lock:
            if transaction_id not in self._pending_transactions:
                if self.visible_interface:
                    logger.warning(f"Transaction not found: {transaction_id}")
                else:
                    logger.debug(f"Transaction not found: {transaction_id}")
                
                return False
            
            if key_index < 0 or key_index >= len(self._verification_keys):
                if self.visible_interface:
                    logger.warning(f"Invalid key index: {key_index}")
                else:
                    logger.debug(f"Invalid key index: {key_index}")
                
                return False
            
            transaction = self._pending_transactions[transaction_id]
            
            if time.time() > transaction["expires_at"]:
                if self.visible_interface:
                    logger.warning(f"Transaction has expired: {transaction_id}")
                else:
                    logger.debug(f"Transaction has expired: {transaction_id}")
                
                return False
            
            if signature is None:
                signature = self._generate_signature(
                    transaction["data"],
                    self._verification_keys[key_index]
                )
            
            transaction["signatures"][str(key_index)] = signature
            
            if self.visible_interface:
                logger.info(f"Added signature to transaction: {transaction_id}")
            else:
                logger.debug(f"Added signature to transaction: {transaction_id}")
            
            if len(transaction["signatures"]) >= self.required_signatures:
                self._verify_transaction(transaction_id)
            
            return True
    
    def _generate_signature(
        self,
        data: Dict[str, Any],
        key: str
    ) -> str:
        """
        Generate a signature for data.
        
        Args:
            data: Data to sign
            key: Key to use for signing
            
        Returns:
            str: Signature
        """
        data_str = json.dumps(data, sort_keys=True)
        key_bytes = base64.b64decode(key)
        
        signature = hmac.new(
            key_bytes,
            data_str.encode(),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode('utf-8')
    
    def _verify_transaction(self, transaction_id: str) -> bool:
        """
        Verify a transaction.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            bool: Whether the transaction was verified
        """
        with self._lock:
            if transaction_id not in self._pending_transactions:
                return False
            
            transaction = self._pending_transactions[transaction_id]
            
            if len(transaction["signatures"]) < self.required_signatures:
                return False
            
            for key_index, signature in transaction["signatures"].items():
                key_index = int(key_index)
                
                if key_index < 0 or key_index >= len(self._verification_keys):
                    continue
                
                expected_signature = self._generate_signature(
                    transaction["data"],
                    self._verification_keys[key_index]
                )
                
                if signature != expected_signature:
                    if self.visible_interface:
                        logger.warning(f"Invalid signature for transaction: {transaction_id}")
                    else:
                        logger.debug(f"Invalid signature for transaction: {transaction_id}")
                    
                    return False
            
            transaction["status"] = "verified"
            transaction["verified_at"] = time.time()
            
            self._verified_transactions[transaction_id] = transaction
            del self._pending_transactions[transaction_id]
            
            if self.visible_interface:
                logger.info(f"Verified transaction: {transaction_id}")
            else:
                logger.debug(f"Verified transaction: {transaction_id}")
            
            return True
    
    def reject_transaction(self, transaction_id: str, reason: str = "") -> bool:
        """
        Reject a transaction.
        
        Args:
            transaction_id: Transaction ID
            reason: Reason for rejection
            
        Returns:
            bool: Whether the transaction was rejected
        """
        with self._lock:
            if transaction_id not in self._pending_transactions:
                return False
            
            transaction = self._pending_transactions[transaction_id]
            
            transaction["status"] = "rejected"
            transaction["rejected_at"] = time.time()
            transaction["rejection_reason"] = reason
            
            self._rejected_transactions[transaction_id] = transaction
            del self._pending_transactions[transaction_id]
            
            if self.visible_interface:
                logger.info(f"Rejected transaction: {transaction_id}")
            else:
                logger.debug(f"Rejected transaction: {transaction_id}")
            
            return True
    
    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a transaction.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            Dict: Transaction data
        """
        with self._lock:
            if transaction_id in self._pending_transactions:
                return self._pending_transactions[transaction_id].copy()
            
            if transaction_id in self._verified_transactions:
                return self._verified_transactions[transaction_id].copy()
            
            if transaction_id in self._rejected_transactions:
                return self._rejected_transactions[transaction_id].copy()
            
            return None
    
    def get_pending_transactions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get pending transactions.
        
        Returns:
            Dict: Pending transactions
        """
        with self._lock:
            return {
                tx_id: tx.copy()
                for tx_id, tx in self._pending_transactions.items()
            }
    
    def get_verified_transactions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get verified transactions.
        
        Returns:
            Dict: Verified transactions
        """
        with self._lock:
            return {
                tx_id: tx.copy()
                for tx_id, tx in self._verified_transactions.items()
            }
    
    def get_rejected_transactions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get rejected transactions.
        
        Returns:
            Dict: Rejected transactions
        """
        with self._lock:
            return {
                tx_id: tx.copy()
                for tx_id, tx in self._rejected_transactions.items()
            }
    
    def cleanup_expired_transactions(self) -> int:
        """
        Clean up expired transactions.
        
        Returns:
            int: Number of expired transactions
        """
        with self._lock:
            current_time = time.time()
            expired_transactions = []
            
            for tx_id, tx in self._pending_transactions.items():
                if current_time > tx["expires_at"]:
                    expired_transactions.append(tx_id)
            
            for tx_id in expired_transactions:
                tx = self._pending_transactions[tx_id]
                
                tx["status"] = "expired"
                tx["expired_at"] = current_time
                
                self._rejected_transactions[tx_id] = tx
                del self._pending_transactions[tx_id]
            
            if expired_transactions and self.visible_interface:
                logger.info(f"Cleaned up {len(expired_transactions)} expired transactions")
            elif expired_transactions:
                logger.debug(f"Cleaned up {len(expired_transactions)} expired transactions")
            
            return len(expired_transactions)

def create_multi_signature_verifier(
    threshold_amount: float = 1000.0,
    required_signatures: int = 2,
    auto_verify_small_transactions: bool = True,
    visible_interface: bool = True
) -> MultiSignatureVerifier:
    """
    Create and return a multi-signature verifier.
    
    Args:
        threshold_amount: Amount threshold for requiring multi-signature
        required_signatures: Number of signatures required for verification
        auto_verify_small_transactions: Whether to auto-verify small transactions
        visible_interface: Whether to show verification messages in the interface
        
    Returns:
        MultiSignatureVerifier: New multi-signature verifier instance
    """
    return MultiSignatureVerifier(
        threshold_amount=threshold_amount,
        required_signatures=required_signatures,
        auto_verify_small_transactions=auto_verify_small_transactions,
        visible_interface=visible_interface
    )
