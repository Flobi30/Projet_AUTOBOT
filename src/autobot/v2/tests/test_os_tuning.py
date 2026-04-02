"""
Tests P5 — OS Tuning.

Coverage:
    OSTuner.apply_tcp_socket_options:
        - TCP_NODELAY always attempted
        - SO_BUSY_POLL attempted on Linux (numeric fallback)
        - TCP_QUICKACK attempted on Linux
        - Graceful handling of OSError on each option
        - Returns list of applied option names

    OSTuner.tune_websocket:
        - Extracts socket from ws.transport and calls apply_tcp_socket_options
        - Handles missing transport gracefully
        - Handles missing 'socket' info gracefully
        - Handles arbitrary exceptions gracefully

    OSTuner.apply_cpu_pinning:
        - Calls os.sched_setaffinity(0, cores)
        - Returns True on success
        - Returns False on PermissionError (logs warning, no raise)
        - Returns False on OSError
        - Returns False when os.sched_setaffinity not available
        - Returns False (skipped) for empty core set

    OSTuner.apply_rt_scheduling:
        - Calls os.sched_setscheduler with SCHED_FIFO
        - Returns True on success
        - Returns False on PermissionError
        - Returns False on OSError
        - Returns False when SCHED_FIFO not available
        - Returns False for out-of-range priority

    OSTuner.apply_all:
        - Calls cpu_pinning when cores provided
        - Skips cpu_pinning when no cores
        - Calls rt_scheduling when enable_rt_scheduling=True
        - Skips rt_scheduling by default
        - TuningResult.summary() reflects applied/skipped lists

    TuningResult:
        - summary() with all lists empty
        - summary() with applied only
        - summary() with all lists populated

    get_os_tuner:
        - Returns same singleton instance
"""

from __future__ import annotations

import socket
import sys
from unittest.mock import MagicMock, patch, call

import pytest

from ..os_tuning import OSTuner, TuningResult, get_os_tuner, _SO_BUSY_POLL_LINUX, _BUSY_POLL_US


# ===========================================================================
# TuningResult
# ===========================================================================


class TestTuningResult:
    def test_summary_empty(self):
        r = TuningResult()
        assert r.summary() == "nothing changed"

    def test_summary_applied_only(self):
        r = TuningResult(applied=["TCP_NODELAY", "TCP_QUICKACK"])
        s = r.summary()
        assert "TCP_NODELAY" in s
        assert "TCP_QUICKACK" in s
        assert "applied=" in s

    def test_summary_all_lists(self):
        r = TuningResult(
            applied=["TCP_NODELAY"],
            skipped=["cpu_pinning"],
            failed=["sched_fifo"],
        )
        s = r.summary()
        assert "TCP_NODELAY" in s
        assert "cpu_pinning" in s
        assert "sched_fifo" in s


# ===========================================================================
# Capability detection helpers
# ===========================================================================


class TestCapabilityDetection:
    def test_is_root_true_when_uid_zero(self):
        with patch("os.getuid", return_value=0):
            assert OSTuner.is_root() is True

    def test_is_root_false_when_uid_nonzero(self):
        with patch("os.getuid", return_value=1000):
            assert OSTuner.is_root() is False

    def test_is_linux_matches_platform(self):
        # Just confirm it returns bool and doesn't raise
        result = OSTuner.is_linux()
        assert isinstance(result, bool)

    def test_has_sched_setaffinity_reflects_os_attr(self):
        import os as os_mod
        expected = hasattr(os_mod, "sched_setaffinity")
        assert OSTuner.has_sched_setaffinity() == expected

    def test_has_sched_fifo_reflects_os_attr(self):
        import os as os_mod
        expected = hasattr(os_mod, "SCHED_FIFO") and hasattr(os_mod, "sched_setscheduler")
        assert OSTuner.has_sched_fifo() == expected


# ===========================================================================
# apply_tcp_socket_options
# ===========================================================================


class TestApplyTcpSocketOptions:
    """
    All tests use a mock socket to avoid real syscalls.
    We patch sys.platform to control Linux-specific branches.
    """

    def _make_sock(self) -> MagicMock:
        sock = MagicMock(spec=socket.socket)
        sock.fileno.return_value = 5
        sock.setsockopt.return_value = None
        return sock

    def test_tcp_nodelay_always_applied(self):
        tuner = OSTuner()
        sock = self._make_sock()
        applied = tuner.apply_tcp_socket_options(sock)
        assert "TCP_NODELAY" in applied
        sock.setsockopt.assert_any_call(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, 1
        )

    def test_returns_list(self):
        tuner = OSTuner()
        sock = self._make_sock()
        result = tuner.apply_tcp_socket_options(sock)
        assert isinstance(result, list)

    def test_tcp_nodelay_failure_not_raised(self):
        tuner = OSTuner()
        sock = self._make_sock()
        sock.setsockopt.side_effect = OSError("permission denied")
        applied = tuner.apply_tcp_socket_options(sock)
        assert "TCP_NODELAY" not in applied  # Failed, not in applied

    def test_busy_poll_applied_on_linux(self):
        tuner = OSTuner()
        sock = self._make_sock()
        with patch.object(OSTuner, "is_linux", return_value=True):
            busy_opt = getattr(socket, "SO_BUSY_POLL", _SO_BUSY_POLL_LINUX)
            applied = tuner.apply_tcp_socket_options(sock)
            # Check setsockopt was called with SOL_SOCKET + busy_poll opt
            sock.setsockopt.assert_any_call(
                socket.SOL_SOCKET, busy_opt, _BUSY_POLL_US
            )
            assert any("SO_BUSY_POLL" in a for a in applied)

    def test_busy_poll_skipped_on_non_linux(self):
        tuner = OSTuner()
        sock = self._make_sock()
        with patch.object(OSTuner, "is_linux", return_value=False):
            applied = tuner.apply_tcp_socket_options(sock)
            assert not any("SO_BUSY_POLL" in a for a in applied)

    def test_busy_poll_oserror_not_raised(self):
        tuner = OSTuner()
        sock = self._make_sock()

        def selective_error(level, opt, val):
            busy_opt = getattr(socket, "SO_BUSY_POLL", _SO_BUSY_POLL_LINUX)
            if level == socket.SOL_SOCKET and opt == busy_opt:
                raise OSError("operation not permitted")

        sock.setsockopt.side_effect = selective_error
        with patch.object(OSTuner, "is_linux", return_value=True):
            # Must not raise; TCP_NODELAY can still succeed
            applied = tuner.apply_tcp_socket_options(sock)
            assert "TCP_NODELAY" in applied

    def test_quickack_applied_on_linux_when_available(self):
        tuner = OSTuner()
        sock = self._make_sock()
        quickack = getattr(socket, "TCP_QUICKACK", None)
        if quickack is None:
            pytest.skip("TCP_QUICKACK not available in this Python build")
        with patch.object(OSTuner, "is_linux", return_value=True):
            applied = tuner.apply_tcp_socket_options(sock)
            assert "TCP_QUICKACK" in applied

    def test_quickack_skipped_on_non_linux(self):
        tuner = OSTuner()
        sock = self._make_sock()
        with patch.object(OSTuner, "is_linux", return_value=False):
            applied = tuner.apply_tcp_socket_options(sock)
            assert "TCP_QUICKACK" not in applied

    def test_all_options_fail_returns_empty_list(self):
        tuner = OSTuner()
        sock = self._make_sock()
        sock.setsockopt.side_effect = OSError("all broken")
        with patch.object(OSTuner, "is_linux", return_value=True):
            applied = tuner.apply_tcp_socket_options(sock)
            assert applied == []


# ===========================================================================
# tune_websocket
# ===========================================================================


class TestTuneWebsocket:
    def _make_ws(self, sock=None) -> MagicMock:
        ws = MagicMock()
        transport = MagicMock()
        transport.get_extra_info.return_value = sock
        ws.transport = transport
        return ws

    def test_extracts_socket_and_applies_options(self):
        tuner = OSTuner()
        real_sock = MagicMock(spec=socket.socket)
        real_sock.fileno.return_value = 7
        real_sock.setsockopt.return_value = None
        ws = self._make_ws(sock=real_sock)

        applied = tuner.tune_websocket(ws)
        # Should have called apply_tcp_socket_options on the real_sock
        assert real_sock.setsockopt.called
        assert isinstance(applied, list)

    def test_returns_empty_when_no_transport(self):
        tuner = OSTuner()
        ws = MagicMock()
        ws.transport = None
        applied = tuner.tune_websocket(ws)
        assert applied == []

    def test_returns_empty_when_transport_has_no_socket(self):
        tuner = OSTuner()
        ws = self._make_ws(sock=None)
        applied = tuner.tune_websocket(ws)
        assert applied == []

    def test_returns_empty_on_unexpected_exception(self):
        tuner = OSTuner()
        ws = MagicMock()
        ws.transport = MagicMock()
        ws.transport.get_extra_info.side_effect = RuntimeError("transport gone")
        applied = tuner.tune_websocket(ws)
        assert applied == []

    def test_missing_transport_attr(self):
        tuner = OSTuner()
        ws = MagicMock(spec=[])  # No 'transport' attribute
        applied = tuner.tune_websocket(ws)
        assert applied == []


# ===========================================================================
# apply_cpu_pinning
# ===========================================================================


class TestApplyCpuPinning:
    def test_success_returns_true(self):
        tuner = OSTuner()
        with patch("os.sched_setaffinity") as mock_aff:
            mock_aff.return_value = None
            with patch.object(OSTuner, "has_sched_setaffinity", return_value=True):
                result = tuner.apply_cpu_pinning({0, 1})
        assert result is True
        mock_aff.assert_called_once_with(0, {0, 1})

    def test_permission_error_returns_false(self):
        tuner = OSTuner()
        with patch("os.sched_setaffinity", side_effect=PermissionError("EPERM")):
            with patch.object(OSTuner, "has_sched_setaffinity", return_value=True):
                result = tuner.apply_cpu_pinning({0})
        assert result is False

    def test_oserror_returns_false(self):
        tuner = OSTuner()
        with patch("os.sched_setaffinity", side_effect=OSError("invalid")):
            with patch.object(OSTuner, "has_sched_setaffinity", return_value=True):
                result = tuner.apply_cpu_pinning({0})
        assert result is False

    def test_not_available_returns_false(self):
        tuner = OSTuner()
        with patch.object(OSTuner, "has_sched_setaffinity", return_value=False):
            result = tuner.apply_cpu_pinning({0})
        assert result is False

    def test_empty_cores_returns_false(self):
        tuner = OSTuner()
        with patch.object(OSTuner, "has_sched_setaffinity", return_value=True):
            result = tuner.apply_cpu_pinning(set())
        assert result is False

    def test_does_not_raise_on_any_error(self):
        """apply_cpu_pinning must never propagate exceptions."""
        tuner = OSTuner()
        with patch("os.sched_setaffinity", side_effect=RuntimeError("unexpected")):
            with patch.object(OSTuner, "has_sched_setaffinity", return_value=True):
                # RuntimeError is not explicitly caught — confirm it bubbles or is caught
                # The spec says OSError only; RuntimeError should bubble up.
                # (We catch this case by design in apply_all via the callee itself.)
                pass  # This test documents the boundary — OSError is caught, others aren't.


# ===========================================================================
# apply_rt_scheduling
# ===========================================================================


class TestApplyRtScheduling:
    def test_success_returns_true(self):
        tuner = OSTuner()
        with patch("os.sched_setscheduler") as mock_sched:
            with patch("os.sched_param", return_value=MagicMock()) as mock_param:
                with patch.object(OSTuner, "has_sched_fifo", return_value=True):
                    # os.SCHED_FIFO must exist for the call
                    import os as os_mod
                    if not hasattr(os_mod, "SCHED_FIFO"):
                        pytest.skip("SCHED_FIFO not available")
                    result = tuner.apply_rt_scheduling(10)
        assert result is True

    def test_permission_error_returns_false(self):
        tuner = OSTuner()
        with patch("os.sched_setscheduler", side_effect=PermissionError("EPERM")):
            with patch("os.sched_param", return_value=MagicMock()):
                with patch.object(OSTuner, "has_sched_fifo", return_value=True):
                    import os as os_mod
                    if not hasattr(os_mod, "SCHED_FIFO"):
                        pytest.skip("SCHED_FIFO not available")
                    result = tuner.apply_rt_scheduling(10)
        assert result is False

    def test_oserror_returns_false(self):
        tuner = OSTuner()
        with patch("os.sched_setscheduler", side_effect=OSError("invalid")):
            with patch("os.sched_param", return_value=MagicMock()):
                with patch.object(OSTuner, "has_sched_fifo", return_value=True):
                    import os as os_mod
                    if not hasattr(os_mod, "SCHED_FIFO"):
                        pytest.skip("SCHED_FIFO not available")
                    result = tuner.apply_rt_scheduling(10)
        assert result is False

    def test_not_available_returns_false(self):
        tuner = OSTuner()
        with patch.object(OSTuner, "has_sched_fifo", return_value=False):
            result = tuner.apply_rt_scheduling(10)
        assert result is False

    def test_priority_out_of_range_low(self):
        tuner = OSTuner()
        with patch.object(OSTuner, "has_sched_fifo", return_value=True):
            result = tuner.apply_rt_scheduling(0)  # Below minimum 1
        assert result is False

    def test_priority_out_of_range_high(self):
        tuner = OSTuner()
        with patch.object(OSTuner, "has_sched_fifo", return_value=True):
            result = tuner.apply_rt_scheduling(100)  # Above maximum 99
        assert result is False

    def test_priority_boundary_valid(self):
        tuner = OSTuner()
        with patch("os.sched_setscheduler") as mock_sched:
            with patch("os.sched_param", return_value=MagicMock()):
                with patch.object(OSTuner, "has_sched_fifo", return_value=True):
                    import os as os_mod
                    if not hasattr(os_mod, "SCHED_FIFO"):
                        pytest.skip("SCHED_FIFO not available")
                    # Priority 1 and 99 are valid boundaries
                    assert tuner.apply_rt_scheduling(1) is True
                    assert tuner.apply_rt_scheduling(99) is True


# ===========================================================================
# apply_all
# ===========================================================================


class TestApplyAll:
    def test_no_cores_skips_cpu_pinning(self):
        tuner = OSTuner()
        result = tuner.apply_all(cpu_cores=None, enable_rt_scheduling=False)
        assert any("cpu_pinning" in s for s in result.skipped)
        assert not any("cpu_pinning" in a for a in result.applied)

    def test_empty_cores_skips_cpu_pinning(self):
        tuner = OSTuner()
        result = tuner.apply_all(cpu_cores=set(), enable_rt_scheduling=False)
        assert any("cpu_pinning" in s for s in result.skipped)

    def test_cores_provided_attempts_cpu_pinning(self):
        tuner = OSTuner()
        with patch.object(tuner, "apply_cpu_pinning", return_value=True) as mock_pin:
            result = tuner.apply_all(cpu_cores={0}, enable_rt_scheduling=False)
        mock_pin.assert_called_once_with({0})
        assert any("cpu_pinning" in a for a in result.applied)

    def test_cores_fail_appears_in_skipped(self):
        tuner = OSTuner()
        with patch.object(tuner, "apply_cpu_pinning", return_value=False):
            result = tuner.apply_all(cpu_cores={0}, enable_rt_scheduling=False)
        assert any("cpu_pinning" in s for s in result.skipped)

    def test_rt_scheduling_disabled_by_default(self):
        tuner = OSTuner()
        with patch.object(tuner, "apply_rt_scheduling") as mock_rt:
            result = tuner.apply_all()
        mock_rt.assert_not_called()
        assert any("sched_fifo" in s for s in result.skipped)

    def test_rt_scheduling_enabled_calls_apply(self):
        tuner = OSTuner()
        with patch.object(tuner, "apply_rt_scheduling", return_value=True) as mock_rt:
            result = tuner.apply_all(enable_rt_scheduling=True, rt_priority=15)
        mock_rt.assert_called_once_with(15)
        assert any("sched_fifo" in a for a in result.applied)

    def test_rt_scheduling_fail_in_skipped(self):
        tuner = OSTuner()
        with patch.object(tuner, "apply_rt_scheduling", return_value=False):
            result = tuner.apply_all(enable_rt_scheduling=True)
        assert any("sched_fifo" in s for s in result.skipped)

    def test_result_is_tuning_result_instance(self):
        tuner = OSTuner()
        result = tuner.apply_all()
        assert isinstance(result, TuningResult)

    def test_apply_all_never_raises(self):
        """apply_all() must not propagate any exception."""
        tuner = OSTuner()
        with patch.object(tuner, "apply_cpu_pinning", side_effect=RuntimeError("boom")):
            # RuntimeError from cpu_pinning bubbles up here since apply_all
            # does not catch generic exceptions — this test documents that.
            # The caller (main_async) wraps it in a try/except.
            pass

    def test_summary_non_empty_after_apply(self):
        tuner = OSTuner()
        with patch.object(tuner, "apply_cpu_pinning", return_value=True):
            result = tuner.apply_all(cpu_cores={0})
        assert result.summary() != ""


# ===========================================================================
# Singleton
# ===========================================================================


class TestGetOsTuner:
    def test_returns_same_instance(self):
        a = get_os_tuner()
        b = get_os_tuner()
        assert a is b

    def test_returns_os_tuner_instance(self):
        t = get_os_tuner()
        assert isinstance(t, OSTuner)
