"""
Deposit and Withdrawal Management for AUTOBOT

This module provides functionality for managing deposits and withdrawals
across multiple exchanges and payment providers.
"""

import logging
import time
import uuid
import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class TransactionStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    PROCESSING = "processing"

class TransactionType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"

@dataclass
class Transaction:
    """Represents a deposit or withdrawal transaction"""
    transaction_id: str
    user_id: str
    type: TransactionType
    amount: float
    currency: str
    status: TransactionStatus
    provider: str
    timestamp: float
    fee: float = 0.0
    destination_address: Optional[str] = None
    source_address: Optional[str] = None
    confirmation_count: int = 0
    required_confirmations: int = 1
    metadata: Optional[Dict[str, Any]] = None


class DepositWithdrawalManager:
    """
    Manages deposits and withdrawals across multiple exchanges and payment providers.
    Provides a unified interface for handling financial transactions.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the deposit/withdrawal manager.
        
        Args:
            config: Configuration dictionary with provider settings
        """
        self.config = config
        self.providers = {}
        self.transactions = {}
        self.callbacks = {}
        
        for provider_name, provider_config in config.get("providers", {}).items():
            self._init_provider(provider_name, provider_config)
        
        logger.info(f"Deposit/Withdrawal Manager initialized with {len(self.providers)} providers")
    
    def _init_provider(self, name: str, config: Dict[str, Any]) -> None:
        """Initialize a payment provider with the given configuration"""
        provider_type = config.get("type", "exchange")
        
        if provider_type == "exchange":
            self.providers[name] = {
                "type": "exchange",
                "config": config,
                "enabled": config.get("enabled", True),
                "deposit_methods": config.get("deposit_methods", ["crypto"]),
                "withdrawal_methods": config.get("withdrawal_methods", ["crypto"]),
                "currencies": config.get("currencies", []),
                "min_deposit": config.get("min_deposit", {}),
                "min_withdrawal": config.get("min_withdrawal", {}),
                "withdrawal_fees": config.get("withdrawal_fees", {})
            }
        elif provider_type == "bank":
            self.providers[name] = {
                "type": "bank",
                "config": config,
                "enabled": config.get("enabled", True),
                "deposit_methods": config.get("deposit_methods", ["sepa", "swift"]),
                "withdrawal_methods": config.get("withdrawal_methods", ["sepa", "swift"]),
                "currencies": config.get("currencies", ["EUR", "USD"]),
                "min_deposit": config.get("min_deposit", {}),
                "min_withdrawal": config.get("min_withdrawal", {}),
                "withdrawal_fees": config.get("withdrawal_fees", {})
            }
        elif provider_type == "payment_processor":
            self.providers[name] = {
                "type": "payment_processor",
                "config": config,
                "enabled": config.get("enabled", True),
                "deposit_methods": config.get("deposit_methods", ["card", "bank"]),
                "withdrawal_methods": config.get("withdrawal_methods", ["card", "bank"]),
                "currencies": config.get("currencies", ["EUR", "USD"]),
                "min_deposit": config.get("min_deposit", {}),
                "min_withdrawal": config.get("min_withdrawal", {}),
                "withdrawal_fees": config.get("withdrawal_fees", {})
            }
        
        logger.info(f"Initialized provider: {name} ({provider_type})")
    
    async def create_deposit(
        self,
        user_id: str,
        amount: float,
        currency: str,
        provider: str,
        method: str = "crypto",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new deposit request.
        
        Args:
            user_id: User ID
            amount: Deposit amount
            currency: Currency code
            provider: Provider name
            method: Deposit method
            metadata: Additional metadata
            
        Returns:
            Dict: Deposit information including address and instructions
        """
        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not found")
        
        if not self.providers[provider]["enabled"]:
            raise ValueError(f"Provider {provider} is disabled")
        
        if method not in self.providers[provider]["deposit_methods"]:
            raise ValueError(f"Method {method} not supported by provider {provider}")
        
        if currency not in self.providers[provider]["currencies"]:
            raise ValueError(f"Currency {currency} not supported by provider {provider}")
        
        min_deposit = self.providers[provider]["min_deposit"].get(currency, 0)
        if amount < min_deposit:
            raise ValueError(f"Minimum deposit amount for {currency} is {min_deposit}")
        
        transaction_id = str(uuid.uuid4())
        
        transaction = Transaction(
            transaction_id=transaction_id,
            user_id=user_id,
            type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status=TransactionStatus.PENDING,
            provider=provider,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        self.transactions[transaction_id] = transaction
        
        deposit_info = await self._get_deposit_address(provider, currency, method)
        
        transaction.destination_address = deposit_info.get("address")
        
        logger.info(f"Created deposit request {transaction_id} for user {user_id}: {amount} {currency} via {provider}")
        
        return {
            "transaction_id": transaction_id,
            "status": transaction.status.value,
            "address": deposit_info.get("address"),
            "memo": deposit_info.get("memo"),
            "instructions": deposit_info.get("instructions"),
            "qr_code": deposit_info.get("qr_code"),
            "expires_at": time.time() + 3600 * 24  # 24 hours
        }
    
    async def _get_deposit_address(self, provider: str, currency: str, method: str) -> Dict[str, Any]:
        """Get a deposit address for the specified provider and currency"""
        
        if self.providers[provider]["type"] == "exchange" and method == "crypto":
            return {
                "address": f"crypto{uuid.uuid4().hex[:16]}",
                "memo": None if currency != "XRP" else str(uuid.uuid4().int)[:9],
                "instructions": f"Send only {currency} to this address",
                "qr_code": f"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
            }
        elif self.providers[provider]["type"] == "bank" and method in ["sepa", "swift"]:
            return {
                "address": None,
                "memo": None,
                "instructions": f"Please transfer to:\nIBAN: DE89370400440532013000\nBIC: COBADEFFXXX\nReference: {uuid.uuid4().hex[:8].upper()}",
                "qr_code": None
            }
        elif self.providers[provider]["type"] == "payment_processor":
            return {
                "address": None,
                "memo": None,
                "instructions": f"Click the link to complete your deposit: https://pay.example.com/{uuid.uuid4().hex}",
                "qr_code": None
            }
        
        raise ValueError(f"Unsupported provider type or method: {provider}/{method}")
    
    async def create_withdrawal(
        self,
        user_id: str,
        amount: float,
        currency: str,
        provider: str,
        destination: str,
        method: str = "crypto",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new withdrawal request.
        
        Args:
            user_id: User ID
            amount: Withdrawal amount
            currency: Currency code
            provider: Provider name
            destination: Destination address or account
            method: Withdrawal method
            metadata: Additional metadata
            
        Returns:
            Dict: Withdrawal information
        """
        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not found")
        
        if not self.providers[provider]["enabled"]:
            raise ValueError(f"Provider {provider} is disabled")
        
        if method not in self.providers[provider]["withdrawal_methods"]:
            raise ValueError(f"Method {method} not supported by provider {provider}")
        
        if currency not in self.providers[provider]["currencies"]:
            raise ValueError(f"Currency {currency} not supported by provider {provider}")
        
        min_withdrawal = self.providers[provider]["min_withdrawal"].get(currency, 0)
        if amount < min_withdrawal:
            raise ValueError(f"Minimum withdrawal amount for {currency} is {min_withdrawal}")
        
        fee = self.providers[provider]["withdrawal_fees"].get(currency, 0)
        
        balance = await self._get_user_balance(user_id, currency)
        if balance < amount + fee:
            raise ValueError(f"Insufficient balance: {balance} {currency} (required: {amount + fee})")
        
        transaction_id = str(uuid.uuid4())
        
        transaction = Transaction(
            transaction_id=transaction_id,
            user_id=user_id,
            type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status=TransactionStatus.PENDING,
            provider=provider,
            timestamp=time.time(),
            fee=fee,
            destination_address=destination,
            metadata=metadata or {}
        )
        
        self.transactions[transaction_id] = transaction
        
        logger.info(f"Created withdrawal request {transaction_id} for user {user_id}: {amount} {currency} via {provider}")
        
        asyncio.create_task(self._process_withdrawal(transaction_id))
        
        return {
            "transaction_id": transaction_id,
            "status": transaction.status.value,
            "amount": amount,
            "fee": fee,
            "net_amount": amount - fee,
            "estimated_completion_time": "10-30 minutes"
        }
    
    async def _get_user_balance(self, user_id: str, currency: str) -> float:
        """Get user balance for the specified currency"""
        return 10000.0
    
    async def _process_withdrawal(self, transaction_id: str) -> None:
        """Process a withdrawal transaction"""
        if transaction_id not in self.transactions:
            logger.error(f"Transaction {transaction_id} not found")
            return
        
        transaction = self.transactions[transaction_id]
        
        try:
            transaction.status = TransactionStatus.PROCESSING
            
            await asyncio.sleep(5)
            
            transaction.status = TransactionStatus.COMPLETED
            transaction.confirmation_count = transaction.required_confirmations
            
            logger.info(f"Withdrawal {transaction_id} completed successfully")
            
            if transaction_id in self.callbacks:
                for callback in self.callbacks[transaction_id]:
                    try:
                        await callback(transaction)
                    except Exception as e:
                        logger.error(f"Error in withdrawal callback: {e}")
            
        except Exception as e:
            logger.error(f"Error processing withdrawal {transaction_id}: {e}")
            transaction.status = TransactionStatus.FAILED
    
    async def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """
        Get transaction details by ID.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            Transaction: Transaction details or None if not found
        """
        return self.transactions.get(transaction_id)
    
    async def get_user_transactions(
        self,
        user_id: str,
        transaction_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Transaction]:
        """
        Get transactions for a specific user.
        
        Args:
            user_id: User ID
            transaction_type: Filter by transaction type
            status: Filter by status
            limit: Maximum number of transactions to return
            offset: Offset for pagination
            
        Returns:
            List[Transaction]: List of transactions
        """
        transactions = []
        
        for tx in self.transactions.values():
            if tx.user_id != user_id:
                continue
            
            if transaction_type and tx.type != transaction_type:
                continue
            
            if status and tx.status != status:
                continue
            
            transactions.append(tx)
        
        transactions.sort(key=lambda x: x.timestamp, reverse=True)
        
        return transactions[offset:offset + limit]
    
    async def register_callback(self, transaction_id: str, callback) -> None:
        """
        Register a callback for transaction status updates.
        
        Args:
            transaction_id: Transaction ID
            callback: Async callback function
        """
        if transaction_id not in self.callbacks:
            self.callbacks[transaction_id] = []
        
        self.callbacks[transaction_id].append(callback)
    
    async def get_deposit_methods(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get available deposit methods for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict: Available deposit methods grouped by provider
        """
        methods = {}
        
        for provider_name, provider in self.providers.items():
            if not provider["enabled"]:
                continue
            
            provider_methods = []
            
            for method in provider["deposit_methods"]:
                provider_methods.append({
                    "method": method,
                    "currencies": provider["currencies"],
                    "min_amounts": provider["min_deposit"]
                })
            
            if provider_methods:
                methods[provider_name] = provider_methods
        
        return methods
    
    async def get_withdrawal_methods(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get available withdrawal methods for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict: Available withdrawal methods grouped by provider
        """
        methods = {}
        
        for provider_name, provider in self.providers.items():
            if not provider["enabled"]:
                continue
            
            provider_methods = []
            
            for method in provider["withdrawal_methods"]:
                provider_methods.append({
                    "method": method,
                    "currencies": provider["currencies"],
                    "min_amounts": provider["min_withdrawal"],
                    "fees": provider["withdrawal_fees"]
                })
            
            if provider_methods:
                methods[provider_name] = provider_methods
        
        return methods


def create_deposit_withdrawal_manager(config: Optional[Dict[str, Any]] = None) -> DepositWithdrawalManager:
    """
    Create a deposit/withdrawal manager with default configuration.
    
    Args:
        config: Optional custom configuration
        
    Returns:
        DepositWithdrawalManager: Configured manager instance
    """
    default_config = {
        "providers": {
            "binance": {
                "type": "exchange",
                "enabled": True,
                "deposit_methods": ["crypto"],
                "withdrawal_methods": ["crypto"],
                "currencies": ["BTC", "ETH", "USDT", "BNB"],
                "min_deposit": {"BTC": 0.0001, "ETH": 0.01, "USDT": 10, "BNB": 0.1},
                "min_withdrawal": {"BTC": 0.0002, "ETH": 0.02, "USDT": 20, "BNB": 0.2},
                "withdrawal_fees": {"BTC": 0.0005, "ETH": 0.005, "USDT": 1, "BNB": 0.01}
            },
            "kraken": {
                "type": "exchange",
                "enabled": True,
                "deposit_methods": ["crypto", "sepa"],
                "withdrawal_methods": ["crypto", "sepa"],
                "currencies": ["BTC", "ETH", "EUR", "USD"],
                "min_deposit": {"BTC": 0.0001, "ETH": 0.01, "EUR": 1, "USD": 1},
                "min_withdrawal": {"BTC": 0.0002, "ETH": 0.02, "EUR": 10, "USD": 10},
                "withdrawal_fees": {"BTC": 0.0005, "ETH": 0.005, "EUR": 0.09, "USD": 0.09}
            },
            "bank_transfer": {
                "type": "bank",
                "enabled": True,
                "deposit_methods": ["sepa", "swift"],
                "withdrawal_methods": ["sepa", "swift"],
                "currencies": ["EUR", "USD", "GBP"],
                "min_deposit": {"EUR": 10, "USD": 10, "GBP": 10},
                "min_withdrawal": {"EUR": 50, "USD": 50, "GBP": 50},
                "withdrawal_fees": {"EUR": 0.8, "USD": 1, "GBP": 0.7}
            },
            "paypal": {
                "type": "payment_processor",
                "enabled": True,
                "deposit_methods": ["card", "bank"],
                "withdrawal_methods": ["card", "bank"],
                "currencies": ["EUR", "USD", "GBP"],
                "min_deposit": {"EUR": 5, "USD": 5, "GBP": 5},
                "min_withdrawal": {"EUR": 10, "USD": 10, "GBP": 10},
                "withdrawal_fees": {"EUR": 1, "USD": 1, "GBP": 1}
            }
        }
    }
    
    if config:
        for provider_name, provider_config in config.get("providers", {}).items():
            if provider_name in default_config["providers"]:
                default_config["providers"][provider_name].update(provider_config)
            else:
                default_config["providers"][provider_name] = provider_config
    
    return DepositWithdrawalManager(default_config)
