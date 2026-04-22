import pytest

from autobot.error_handler import (
    CircuitBreakerOpenError,
    CircuitState,
    ErrorHandler,
)


def test_circuit_opens_only_after_consecutive_failures_with_resets():
    handler = ErrorHandler(
        max_retries=1,
        circuit_failure_threshold=3,
        retry_delay=0,
    )

    def fail_once():
        raise RuntimeError("boom")

    def succeed():
        return "ok"

    # échec, succès, échec, succès
    with pytest.raises(RuntimeError):
        handler.execute_with_retry(fail_once)
    assert handler._failure_count == 1
    assert handler.circuit_state == CircuitState.CLOSED

    assert handler.execute_with_retry(succeed) == "ok"
    assert handler._failure_count == 0
    assert handler.circuit_state == CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        handler.execute_with_retry(fail_once)
    assert handler._failure_count == 1
    assert handler.circuit_state == CircuitState.CLOSED

    assert handler.execute_with_retry(succeed) == "ok"
    assert handler._failure_count == 0
    assert handler.circuit_state == CircuitState.CLOSED

    # puis échecs successifs -> ouverture uniquement au seuil
    with pytest.raises(RuntimeError):
        handler.execute_with_retry(fail_once)
    assert handler._failure_count == 1
    assert handler.circuit_state == CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        handler.execute_with_retry(fail_once)
    assert handler._failure_count == 2
    assert handler.circuit_state == CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        handler.execute_with_retry(fail_once)
    assert handler._failure_count == 3
    assert handler.circuit_state == CircuitState.OPEN


def test_execute_with_retry_keeps_raising_circuit_breaker_on_error_cascade(monkeypatch):
    handler = ErrorHandler(
        max_retries=5,
        circuit_failure_threshold=2,
        retry_delay=0,
    )

    monkeypatch.setattr("autobot.error_handler.time.sleep", lambda _delay: None)

    def always_fail():
        raise RuntimeError("cascade")

    with pytest.raises(CircuitBreakerOpenError, match="Circuit ouvert après 2 échecs"):
        handler.execute_with_retry(always_fail)

    assert handler.circuit_state == CircuitState.OPEN
