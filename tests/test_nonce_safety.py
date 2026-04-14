import asyncio
from concurrent.futures import ThreadPoolExecutor

from autobot.v2.order_executor_async import OrderExecutorAsync
from autobot.v2.nonce_manager import NonceManager


def test_nonce_generator_monotonic_under_concurrency(tmp_path):
    nm = NonceManager(str(tmp_path / "nonce.db"))

    def _next():
        return nm.next_nonce("api-key-1")

    with ThreadPoolExecutor(max_workers=8) as ex:
        values = list(ex.map(lambda _: _next(), range(200)))

    assert len(values) == len(set(values))
    # Concurrency can reorder return completion, but generated values must be strictly increasing globally.
    sorted_values = sorted(values)
    assert all(sorted_values[i] < sorted_values[i + 1] for i in range(len(sorted_values) - 1))


def test_repeated_invalid_nonce_triggers_circuit_breaker(monkeypatch):
    async def _run():
        tripped = {"v": False}

        async def cb():
            tripped["v"] = True

        ex = OrderExecutorAsync(api_key="k", api_secret="c2VjcmV0")
        ex.set_circuit_breaker_callback(cb)

        async def fake_query_private(method, **params):
            return {"error": ["EAPI:Invalid nonce"]}

        monkeypatch.setattr(ex, "_query_private", fake_query_private)
        monkeypatch.setattr(ex, "_rate_limit", lambda: asyncio.sleep(0))

        for _ in range(3):
            ok, _ = await ex._safe_api_call("Balance", max_retries=1)
            assert ok is False

        assert tripped["v"] is True

    asyncio.run(_run())
