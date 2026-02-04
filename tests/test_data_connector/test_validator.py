"""Tests for Data Validator module."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import sys
sys.path.insert(0, "/home/ubuntu/Projet_AUTOBOT/src")

from data_connector.validator import (
    ValidationSeverity,
    ValidationIssue,
    ValidationResult,
    ValidationRule,
    DataValidator,
    AnomalyDetector,
)
from data_connector.base import MarketData


class TestValidationSeverity:
    """Tests for ValidationSeverity enum."""
    
    def test_all_severities_exist(self):
        """Test that all expected severities exist."""
        expected = ["INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for severity in expected:
            assert hasattr(ValidationSeverity, severity)


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""
    
    def test_issue_creation(self):
        """Test basic issue creation."""
        issue = ValidationIssue(
            field="price",
            message="Price is negative",
            severity=ValidationSeverity.ERROR,
            value=-100.0,
            rule_name="price_positive",
        )
        
        assert issue.field == "price"
        assert issue.message == "Price is negative"
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.value == -100.0
        assert issue.rule_name == "price_positive"
    
    def test_issue_to_dict(self):
        """Test issue to_dict conversion."""
        issue = ValidationIssue(
            field="volume",
            message="Volume is negative",
            severity=ValidationSeverity.WARNING,
            value=-500,
        )
        
        result = issue.to_dict()
        
        assert result["field"] == "volume"
        assert result["message"] == "Volume is negative"
        assert result["severity"] == "WARNING"
        assert result["value"] == "-500"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_valid_result(self):
        """Test valid result creation."""
        result = ValidationResult(is_valid=True)
        
        assert result.is_valid is True
        assert len(result.issues) == 0
        assert result.has_errors is False
        assert result.has_warnings is False
    
    def test_invalid_result_with_errors(self):
        """Test invalid result with errors."""
        issues = [
            ValidationIssue(
                field="price",
                message="Price is negative",
                severity=ValidationSeverity.ERROR,
            ),
        ]
        
        result = ValidationResult(is_valid=False, issues=issues)
        
        assert result.is_valid is False
        assert result.has_errors is True
        assert len(result.errors) == 1
    
    def test_result_with_warnings(self):
        """Test result with warnings only."""
        issues = [
            ValidationIssue(
                field="timestamp",
                message="Timestamp is old",
                severity=ValidationSeverity.WARNING,
            ),
        ]
        
        result = ValidationResult(is_valid=True, issues=issues)
        
        assert result.is_valid is True
        assert result.has_warnings is True
        assert result.has_errors is False
        assert len(result.warnings) == 1
    
    def test_result_to_dict(self):
        """Test result to_dict conversion."""
        issues = [
            ValidationIssue(
                field="price",
                message="Test",
                severity=ValidationSeverity.ERROR,
            ),
            ValidationIssue(
                field="volume",
                message="Test",
                severity=ValidationSeverity.WARNING,
            ),
        ]
        
        result = ValidationResult(is_valid=False, issues=issues)
        
        data = result.to_dict()
        
        assert data["is_valid"] is False
        assert data["error_count"] == 1
        assert data["warning_count"] == 1
        assert len(data["issues"]) == 2


class TestValidationRule:
    """Tests for ValidationRule dataclass."""
    
    def test_rule_creation(self):
        """Test basic rule creation."""
        rule = ValidationRule(
            name="test_rule",
            field="price",
            validator=lambda v, _: v > 0,
            message="Price must be positive",
        )
        
        assert rule.name == "test_rule"
        assert rule.field == "price"
        assert rule.enabled is True
    
    def test_rule_validate_pass(self):
        """Test rule validation that passes."""
        rule = ValidationRule(
            name="positive_price",
            field="price",
            validator=lambda v, _: v > 0,
            message="Price must be positive",
        )
        
        issue = rule.validate(100.0)
        
        assert issue is None
    
    def test_rule_validate_fail(self):
        """Test rule validation that fails."""
        rule = ValidationRule(
            name="positive_price",
            field="price",
            validator=lambda v, _: v > 0,
            message="Price must be positive",
        )
        
        issue = rule.validate(-100.0)
        
        assert issue is not None
        assert issue.field == "price"
        assert issue.message == "Price must be positive"
    
    def test_rule_disabled(self):
        """Test disabled rule."""
        rule = ValidationRule(
            name="test",
            field="price",
            validator=lambda v, _: False,
            message="Always fails",
            enabled=False,
        )
        
        issue = rule.validate(100.0)
        
        assert issue is None
    
    def test_rule_with_context(self):
        """Test rule with context."""
        rule = ValidationRule(
            name="ask_gte_bid",
            field="ask",
            validator=lambda v, ctx: v >= ctx.bid if ctx and ctx.bid else True,
            message="Ask must be >= bid",
        )
        
        context = MagicMock()
        context.bid = 100.0
        
        issue = rule.validate(99.0, context)
        
        assert issue is not None
    
    def test_rule_exception_handling(self):
        """Test rule handles exceptions."""
        rule = ValidationRule(
            name="bad_rule",
            field="price",
            validator=lambda v, _: 1/0,
            message="Will fail",
        )
        
        issue = rule.validate(100.0)
        
        assert issue is not None
        assert "Validation error" in issue.message


class TestDataValidator:
    """Tests for DataValidator class."""
    
    def test_validator_creation(self):
        """Test validator creation."""
        validator = DataValidator()
        
        assert validator is not None
        assert validator.strict_mode is False
    
    def test_validator_strict_mode(self):
        """Test validator in strict mode."""
        validator = DataValidator(strict_mode=True)
        
        assert validator.strict_mode is True
    
    def test_validate_valid_data(self):
        """Test validating valid market data."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            bid=150.0,
            ask=150.5,
            last=150.25,
            volume=1000000.0,
        )
        
        result = validator.validate(data)
        
        assert result.is_valid is True
    
    def test_validate_missing_symbol(self):
        """Test validating data with missing symbol."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="",
            timestamp=datetime.utcnow(),
        )
        
        result = validator.validate(data)
        
        assert result.is_valid is False
        assert any(i.field == "symbol" for i in result.issues)
    
    def test_validate_negative_price(self):
        """Test validating data with negative price."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=-100.0,
        )
        
        result = validator.validate(data)
        
        assert any(i.field == "last" for i in result.issues)
    
    def test_validate_negative_volume(self):
        """Test validating data with negative volume."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            volume=-1000.0,
        )
        
        result = validator.validate(data)
        
        assert any(i.field == "volume" for i in result.issues)
    
    def test_validate_bid_ask_spread(self):
        """Test validating bid/ask spread."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            bid=151.0,
            ask=150.0,
        )
        
        result = validator.validate(data)
        
        assert any("bid" in i.message.lower() or "ask" in i.message.lower() for i in result.issues)
    
    def test_validate_high_low_consistency(self):
        """Test validating high/low consistency."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            high=100.0,
            low=110.0,
        )
        
        result = validator.validate(data)
        
        assert any(i.field == "high" for i in result.issues)
    
    def test_validate_dict_input(self):
        """Test validating dictionary input."""
        validator = DataValidator()
        
        data = {
            "symbol": "AAPL",
            "timestamp": datetime.utcnow().isoformat(),
            "last": 150.0,
        }
        
        result = validator.validate(data)
        
        assert result.is_valid is True
    
    def test_validate_batch(self):
        """Test batch validation."""
        validator = DataValidator()
        
        data_list = [
            MarketData(symbol="AAPL", timestamp=datetime.utcnow(), last=150.0),
            MarketData(symbol="GOOGL", timestamp=datetime.utcnow(), last=2800.0),
            MarketData(symbol="", timestamp=datetime.utcnow()),
        ]
        
        results = validator.validate_batch(data_list)
        
        assert len(results) == 3
        assert results[0].is_valid is True
        assert results[1].is_valid is True
        assert results[2].is_valid is False
    
    def test_add_rule(self):
        """Test adding a custom rule."""
        validator = DataValidator()
        
        rule = ValidationRule(
            name="custom_rule",
            field="last",
            validator=lambda v, _: v is None or v < 1000000,
            message="Price too high",
        )
        
        validator.add_rule(rule)
        
        rules = validator.get_rules()
        assert any(r["name"] == "custom_rule" for r in rules)
    
    def test_remove_rule(self):
        """Test removing a rule."""
        validator = DataValidator()
        
        result = validator.remove_rule("symbol_required")
        
        assert result is True
        
        rules = validator.get_rules()
        assert not any(r["name"] == "symbol_required" for r in rules)
    
    def test_enable_disable_rule(self):
        """Test enabling and disabling rules."""
        validator = DataValidator()
        
        validator.disable_rule("symbol_required")
        
        data = MarketData(symbol="", timestamp=datetime.utcnow())
        result = validator.validate(data)
        
        assert not any(i.rule_name == "symbol_required" for i in result.issues)
        
        validator.enable_rule("symbol_required")
        
        result = validator.validate(data)
        assert any(i.rule_name == "symbol_required" for i in result.issues)
    
    def test_sanitize(self):
        """Test data sanitization."""
        validator = DataValidator()
        
        data = MarketData(
            symbol="  aapl  ",
            timestamp=datetime.utcnow(),
            last=-150.0,
            volume=-1000.0,
        )
        
        sanitized = validator.sanitize(data)
        
        assert sanitized.symbol == "AAPL"
        assert sanitized.last == 150.0
        assert sanitized.volume == 1000.0
    
    def test_sanitize_dict(self):
        """Test sanitizing dictionary input."""
        validator = DataValidator()
        
        data = {
            "symbol": "  btc/usd  ",
            "timestamp": datetime.utcnow().isoformat(),
            "last": -50000.0,
        }
        
        sanitized = validator.sanitize(data)
        
        assert sanitized["symbol"] == "BTC/USD"
        assert sanitized["last"] == 50000.0
    
    def test_get_rules(self):
        """Test getting all rules."""
        validator = DataValidator()
        
        rules = validator.get_rules()
        
        assert len(rules) > 0
        assert all("name" in r for r in rules)
        assert all("field" in r for r in rules)
        assert all("enabled" in r for r in rules)


class TestAnomalyDetector:
    """Tests for AnomalyDetector class."""
    
    def test_detector_creation(self):
        """Test anomaly detector creation."""
        detector = AnomalyDetector()
        
        assert detector is not None
        assert detector.window_size == 100
        assert detector.z_score_threshold == 3.0
    
    def test_detector_custom_params(self):
        """Test detector with custom parameters."""
        detector = AnomalyDetector(
            window_size=50,
            z_score_threshold=2.5,
            price_change_threshold=0.05,
        )
        
        assert detector.window_size == 50
        assert detector.z_score_threshold == 2.5
        assert detector.price_change_threshold == 0.05
    
    def test_check_normal_data(self):
        """Test checking normal data."""
        detector = AnomalyDetector()
        
        for i in range(20):
            data = MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                last=150.0 + (i * 0.1),
            )
            issues = detector.check(data)
        
        assert len(issues) == 0
    
    def test_check_large_price_change(self):
        """Test detecting large price change."""
        detector = AnomalyDetector(price_change_threshold=0.05)
        
        data1 = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=100.0,
        )
        detector.check(data1)
        
        data2 = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=120.0,
        )
        issues = detector.check(data2)
        
        assert len(issues) > 0
        assert any("price change" in i.message.lower() for i in issues)
    
    def test_check_z_score_anomaly(self):
        """Test detecting z-score anomaly."""
        detector = AnomalyDetector(z_score_threshold=2.0)
        
        for i in range(20):
            data = MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                last=100.0,
            )
            detector.check(data)
        
        data_anomaly = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=200.0,
        )
        issues = detector.check(data_anomaly)
        
        assert len(issues) > 0
    
    def test_check_multiple_symbols(self):
        """Test checking multiple symbols independently."""
        detector = AnomalyDetector()
        
        for i in range(10):
            data_aapl = MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                last=150.0,
            )
            data_googl = MarketData(
                symbol="GOOGL",
                timestamp=datetime.utcnow(),
                last=2800.0,
            )
            detector.check(data_aapl)
            detector.check(data_googl)
        
        data_aapl_anomaly = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=300.0,
        )
        issues = detector.check(data_aapl_anomaly)
        
        assert len(issues) > 0
    
    def test_reset_symbol(self):
        """Test resetting history for a symbol."""
        detector = AnomalyDetector()
        
        for i in range(10):
            data = MarketData(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                last=150.0,
            )
            detector.check(data)
        
        detector.reset("AAPL")
        
        data_new = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=300.0,
        )
        issues = detector.check(data_new)
        
        assert len(issues) == 0
    
    def test_reset_all(self):
        """Test resetting all history."""
        detector = AnomalyDetector()
        
        for symbol in ["AAPL", "GOOGL", "MSFT"]:
            for i in range(10):
                data = MarketData(
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    last=100.0,
                )
                detector.check(data)
        
        detector.reset()
        
        for symbol in ["AAPL", "GOOGL", "MSFT"]:
            data = MarketData(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                last=200.0,
            )
            issues = detector.check(data)
            assert len(issues) == 0
    
    def test_check_with_close_price(self):
        """Test checking with close price when last is None."""
        detector = AnomalyDetector()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            close=150.0,
        )
        
        issues = detector.check(data)
        
        assert isinstance(issues, list)
    
    def test_check_no_price(self):
        """Test checking data with no price."""
        detector = AnomalyDetector()
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
        )
        
        issues = detector.check(data)
        
        assert len(issues) == 0
