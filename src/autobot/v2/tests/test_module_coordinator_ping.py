from types import SimpleNamespace

import pytest

from autobot.v2 import module_coordinator as module_coordinator_mod
from autobot.v2.module_coordinator import ModuleCoordinator


pytestmark = pytest.mark.unit


def _make_coordinator() -> ModuleCoordinator:
    orchestrator = SimpleNamespace(
        _module_backoff={},
        hardening_flags={},
        _record_module_event=lambda *_args, **_kwargs: None,
    )
    return ModuleCoordinator(orchestrator=orchestrator)


def test_quick_ping_uses_validated_ip_without_second_dns_resolution(monkeypatch):
    coordinator = _make_coordinator()
    dns_calls = {"count": 0}
    first_ip = "93.184.216.34"
    second_ip = "203.0.113.10"

    def fake_getaddrinfo(host, port, type):  # noqa: A002
        dns_calls["count"] += 1
        resolved_ip = first_ip if dns_calls["count"] == 1 else second_ip
        return [(None, None, None, None, (resolved_ip, port))]

    class _FakeSocket:
        def __init__(self, peer_ip: str) -> None:
            self._peer_ip = peer_ip

        def getpeername(self):
            return (self._peer_ip, 443)

    class _FakeResponse:
        status = 200

    class _FakePinnedConnection:
        target_ip_seen = None

        def __init__(self, host: str, target_ip: str, timeout: float) -> None:
            self.host = host
            self.sock = _FakeSocket(target_ip)
            self.__class__.target_ip_seen = target_ip

        def request(self, method: str, path: str, headers: dict[str, str]) -> None:
            assert method == "HEAD"
            assert headers["Host"] == self.host

        def getresponse(self):
            return _FakeResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr(module_coordinator_mod.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(module_coordinator_mod, "_PinnedIPHTTPSConnection", _FakePinnedConnection)

    ok = coordinator._quick_ping("https://api.twitter.com/healthz")

    assert ok is True
    assert dns_calls["count"] == 1
    assert _FakePinnedConnection.target_ip_seen == first_ip
