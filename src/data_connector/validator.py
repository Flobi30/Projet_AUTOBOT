"""
Data Validator for Data Connector.

Implements comprehensive data validation with configurable rules.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .base import MarketData

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class ValidationIssue:
    """A single validation issue."""
    field: str
    message: str
    severity: ValidationSeverity
    value: Any = None
    rule_name: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity.name,
            "value": str(self.value) if self.value is not None else None,
            "rule_name": self.rule_name,
        }


@dataclass
class ValidationResult:
    """Result of data validation."""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    data: Optional[Any] = None
    validated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def errors(self) -> List[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "validated_at": self.validated_at.isoformat(),
        }


@dataclass
class ValidationRule:
    """A validation rule definition."""
    name: str
    field: str
    validator: Callable[[Any, Any], bool]
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    enabled: bool = True
    
    def validate(self, value: Any, context: Any = None) -> Optional[ValidationIssue]:
        """
        Run the validation rule.
        
        Args:
            value: Value to validate
            context: Optional context (e.g., full data object)
            
        Returns:
            ValidationIssue if validation fails, None otherwise
        """
        if not self.enabled:
            return None
        
        try:
            if not self.validator(value, context):
                return ValidationIssue(
                    field=self.field,
                    message=self.message,
                    severity=self.severity,
                    value=value,
                    rule_name=self.name,
                )
        except Exception as e:
            return ValidationIssue(
                field=self.field,
                message=f"Validation error: {str(e)}",
                severity=ValidationSeverity.ERROR,
                value=value,
                rule_name=self.name,
            )
        
        return None


class DataValidator:
    """
    Comprehensive data validator for market data.
    
    Features:
    - Configurable validation rules
    - Multiple severity levels
    - Field-level and cross-field validation
    - Anomaly detection
    - Data sanitization
    """
    
    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
        self._rules: List[ValidationRule] = []
        self._field_rules: Dict[str, List[ValidationRule]] = {}
        
        self._setup_default_rules()
        
        logger.info(f"DataValidator initialized (strict_mode={strict_mode})")
    
    def _setup_default_rules(self) -> None:
        """Setup default validation rules for market data."""
        self.add_rule(ValidationRule(
            name="symbol_required",
            field="symbol",
            validator=lambda v, _: v is not None and len(str(v).strip()) > 0,
            message="Symbol is required and cannot be empty",
            severity=ValidationSeverity.CRITICAL,
        ))
        
        self.add_rule(ValidationRule(
            name="symbol_format",
            field="symbol",
            validator=lambda v, _: v is None or re.match(r'^[A-Z0-9/._-]+$', str(v).upper()),
            message="Symbol contains invalid characters",
            severity=ValidationSeverity.ERROR,
        ))
        
        self.add_rule(ValidationRule(
            name="timestamp_required",
            field="timestamp",
            validator=lambda v, _: v is not None,
            message="Timestamp is required",
            severity=ValidationSeverity.CRITICAL,
        ))
        
        self.add_rule(ValidationRule(
            name="timestamp_not_future",
            field="timestamp",
            validator=lambda v, _: v is None or v <= datetime.utcnow() + timedelta(minutes=5),
            message="Timestamp cannot be in the future",
            severity=ValidationSeverity.WARNING,
        ))
        
        self.add_rule(ValidationRule(
            name="timestamp_not_stale",
            field="timestamp",
            validator=lambda v, _: v is None or v >= datetime.utcnow() - timedelta(days=365),
            message="Timestamp is too old (>1 year)",
            severity=ValidationSeverity.WARNING,
        ))
        
        for price_field in ["bid", "ask", "last", "open", "high", "low", "close", "vwap"]:
            self.add_rule(ValidationRule(
                name=f"{price_field}_positive",
                field=price_field,
                validator=lambda v, _: v is None or v >= 0,
                message=f"{price_field.capitalize()} price cannot be negative",
                severity=ValidationSeverity.ERROR,
            ))
            
            self.add_rule(ValidationRule(
                name=f"{price_field}_reasonable",
                field=price_field,
                validator=lambda v, _: v is None or v < 1e12,
                message=f"{price_field.capitalize()} price is unreasonably high",
                severity=ValidationSeverity.WARNING,
            ))
        
        self.add_rule(ValidationRule(
            name="volume_positive",
            field="volume",
            validator=lambda v, _: v is None or v >= 0,
            message="Volume cannot be negative",
            severity=ValidationSeverity.ERROR,
        ))
        
        self.add_rule(ValidationRule(
            name="bid_ask_spread",
            field="ask",
            validator=lambda v, ctx: (
                v is None or 
                ctx is None or 
                getattr(ctx, 'bid', None) is None or 
                v >= ctx.bid
            ),
            message="Ask price should be >= bid price",
            severity=ValidationSeverity.WARNING,
        ))
        
        self.add_rule(ValidationRule(
            name="high_low_consistency",
            field="high",
            validator=lambda v, ctx: (
                v is None or 
                ctx is None or 
                getattr(ctx, 'low', None) is None or 
                v >= ctx.low
            ),
            message="High price should be >= low price",
            severity=ValidationSeverity.ERROR,
        ))
        
        self.add_rule(ValidationRule(
            name="ohlc_high_consistency",
            field="high",
            validator=lambda v, ctx: (
                v is None or 
                ctx is None or 
                (
                    (getattr(ctx, 'open', None) is None or v >= ctx.open) and
                    (getattr(ctx, 'close', None) is None or v >= ctx.close)
                )
            ),
            message="High should be >= open and close",
            severity=ValidationSeverity.WARNING,
        ))
        
        self.add_rule(ValidationRule(
            name="ohlc_low_consistency",
            field="low",
            validator=lambda v, ctx: (
                v is None or 
                ctx is None or 
                (
                    (getattr(ctx, 'open', None) is None or v <= ctx.open) and
                    (getattr(ctx, 'close', None) is None or v <= ctx.close)
                )
            ),
            message="Low should be <= open and close",
            severity=ValidationSeverity.WARNING,
        ))
    
    def add_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule."""
        self._rules.append(rule)
        
        if rule.field not in self._field_rules:
            self._field_rules[rule.field] = []
        self._field_rules[rule.field].append(rule)
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a validation rule by name."""
        for rule in self._rules[:]:
            if rule.name == rule_name:
                self._rules.remove(rule)
                if rule.field in self._field_rules:
                    self._field_rules[rule.field] = [
                        r for r in self._field_rules[rule.field]
                        if r.name != rule_name
                    ]
                return True
        return False
    
    def enable_rule(self, rule_name: str) -> bool:
        """Enable a validation rule."""
        for rule in self._rules:
            if rule.name == rule_name:
                rule.enabled = True
                return True
        return False
    
    def disable_rule(self, rule_name: str) -> bool:
        """Disable a validation rule."""
        for rule in self._rules:
            if rule.name == rule_name:
                rule.enabled = False
                return True
        return False
    
    def validate(self, data: Union[MarketData, Dict[str, Any]]) -> ValidationResult:
        """
        Validate market data.
        
        Args:
            data: MarketData object or dictionary
            
        Returns:
            ValidationResult with validation status and issues
        """
        issues: List[ValidationIssue] = []
        
        if isinstance(data, dict):
            data_dict = data
            context = None
        else:
            data_dict = data.to_dict() if hasattr(data, 'to_dict') else {}
            context = data
        
        for rule in self._rules:
            if not rule.enabled:
                continue
            
            value = data_dict.get(rule.field) if isinstance(data_dict, dict) else getattr(data, rule.field, None)
            
            issue = rule.validate(value, context or data)
            if issue:
                issues.append(issue)
        
        has_critical = any(i.severity == ValidationSeverity.CRITICAL for i in issues)
        has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)
        
        is_valid = not has_critical and (not has_errors or not self.strict_mode)
        
        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            data=data,
        )
    
    def validate_batch(self, data_list: List[Union[MarketData, Dict[str, Any]]]) -> List[ValidationResult]:
        """
        Validate a batch of market data.
        
        Args:
            data_list: List of MarketData objects or dictionaries
            
        Returns:
            List of ValidationResult objects
        """
        return [self.validate(data) for data in data_list]
    
    def sanitize(self, data: Union[MarketData, Dict[str, Any]]) -> Union[MarketData, Dict[str, Any]]:
        """
        Sanitize market data by fixing common issues.
        
        Args:
            data: MarketData object or dictionary
            
        Returns:
            Sanitized data
        """
        if isinstance(data, dict):
            sanitized = data.copy()
        else:
            sanitized = data.to_dict()
        
        if "symbol" in sanitized and sanitized["symbol"]:
            sanitized["symbol"] = str(sanitized["symbol"]).upper().strip()
        
        for price_field in ["bid", "ask", "last", "open", "high", "low", "close", "vwap"]:
            if price_field in sanitized and sanitized[price_field] is not None:
                try:
                    sanitized[price_field] = abs(float(sanitized[price_field]))
                except (ValueError, TypeError):
                    sanitized[price_field] = None
        
        if "volume" in sanitized and sanitized["volume"] is not None:
            try:
                sanitized["volume"] = abs(float(sanitized["volume"]))
            except (ValueError, TypeError):
                sanitized["volume"] = None
        
        if isinstance(data, MarketData):
            return MarketData.from_dict(sanitized)
        
        return sanitized
    
    def get_rules(self) -> List[Dict[str, Any]]:
        """Get all validation rules."""
        return [
            {
                "name": rule.name,
                "field": rule.field,
                "message": rule.message,
                "severity": rule.severity.name,
                "enabled": rule.enabled,
            }
            for rule in self._rules
        ]


class AnomalyDetector:
    """
    Detects anomalies in market data streams.
    
    Uses statistical methods to identify outliers and
    suspicious data points.
    """
    
    def __init__(
        self,
        window_size: int = 100,
        z_score_threshold: float = 3.0,
        price_change_threshold: float = 0.1,
    ):
        self.window_size = window_size
        self.z_score_threshold = z_score_threshold
        self.price_change_threshold = price_change_threshold
        
        self._price_history: Dict[str, List[float]] = {}
        self._volume_history: Dict[str, List[float]] = {}
    
    def _update_history(self, symbol: str, price: float, volume: Optional[float]) -> None:
        """Update price and volume history for a symbol."""
        if symbol not in self._price_history:
            self._price_history[symbol] = []
            self._volume_history[symbol] = []
        
        self._price_history[symbol].append(price)
        if len(self._price_history[symbol]) > self.window_size:
            self._price_history[symbol].pop(0)
        
        if volume is not None:
            self._volume_history[symbol].append(volume)
            if len(self._volume_history[symbol]) > self.window_size:
                self._volume_history[symbol].pop(0)
    
    def _calculate_z_score(self, value: float, history: List[float]) -> float:
        """Calculate z-score for a value given history."""
        if len(history) < 2:
            return 0.0
        
        import statistics
        mean = statistics.mean(history)
        stdev = statistics.stdev(history)
        
        if stdev == 0:
            return 0.0
        
        return (value - mean) / stdev
    
    def check(self, data: MarketData) -> List[ValidationIssue]:
        """
        Check for anomalies in market data.
        
        Args:
            data: MarketData to check
            
        Returns:
            List of ValidationIssue for any detected anomalies
        """
        issues: List[ValidationIssue] = []
        
        price = data.last or data.close
        if price is None:
            return issues
        
        symbol = data.symbol
        
        if symbol in self._price_history and len(self._price_history[symbol]) > 0:
            last_price = self._price_history[symbol][-1]
            price_change = abs(price - last_price) / last_price if last_price > 0 else 0
            
            if price_change > self.price_change_threshold:
                issues.append(ValidationIssue(
                    field="last",
                    message=f"Large price change detected: {price_change:.2%}",
                    severity=ValidationSeverity.WARNING,
                    value=price,
                    rule_name="price_change_anomaly",
                ))
            
            if len(self._price_history[symbol]) >= 10:
                z_score = self._calculate_z_score(price, self._price_history[symbol])
                
                if abs(z_score) > self.z_score_threshold:
                    issues.append(ValidationIssue(
                        field="last",
                        message=f"Price z-score anomaly: {z_score:.2f}",
                        severity=ValidationSeverity.WARNING,
                        value=price,
                        rule_name="price_zscore_anomaly",
                    ))
        
        if data.volume is not None and symbol in self._volume_history:
            if len(self._volume_history[symbol]) >= 10:
                z_score = self._calculate_z_score(data.volume, self._volume_history[symbol])
                
                if abs(z_score) > self.z_score_threshold:
                    issues.append(ValidationIssue(
                        field="volume",
                        message=f"Volume z-score anomaly: {z_score:.2f}",
                        severity=ValidationSeverity.INFO,
                        value=data.volume,
                        rule_name="volume_zscore_anomaly",
                    ))
        
        self._update_history(symbol, price, data.volume)
        
        return issues
    
    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset anomaly detection history."""
        if symbol:
            self._price_history.pop(symbol, None)
            self._volume_history.pop(symbol, None)
        else:
            self._price_history.clear()
            self._volume_history.clear()
