import pytest

import asyncio
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor

from autobot.v2.order_executor_async import OrderExecutorAsync
from autobot.v2.nonce_manager import NonceManager


pytestmark = pytest.mark.integration

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


def _reserve_in_process(db_path: str, api_key_id: str, count: int) -> list[int]:
    nm = NonceManager(db_path)
    return [nm.next_nonce(api_key_id) for _ in range(count)]


def test_nonce_generator_monotonic_under_multi_process(tmp_path):
    db_path = str(tmp_path / "nonce-multiprocess.db")
    workers = 4
    per_worker = 80

    with mp.Pool(processes=workers) as pool:
        batches = pool.starmap(
            _reserve_in_process,
            [(db_path, "api-key-1", per_worker) for _ in range(workers)],
        )

    values = [nonce for batch in batches for nonce in batch]
    assert len(values) == workers * per_worker
    assert len(values) == len(set(values))
    sorted_values = sorted(values)
    assert all(sorted_values[i] < sorted_values[i + 1] for i in range(len(sorted_values) - 1))


def test_order_executor_uses_reserved_local_nonce_range():
    async def _run():
        class FakeNonceManager:
            def __init__(self) -> None:
                self.calls = 0

            def reserve_range(self, _api_key_id: str, block_size: int = 64):
                start = self.calls * block_size + 1_000_000
                self.calls += 1
                return start, start + block_size - 1

            def next_nonce(self, _api_key_id: str) -> int:
                raise AssertionError("next_nonce should not be used by async executor")

        fake = FakeNonceManager()
        ex = OrderExecutorAsync(api_key="k", api_secret="c2VjcmV0", nonce_manager=fake)

        values = await asyncio.gather(*[ex._next_nonce("api-key-1") for _ in range(130)])
        assert values == sorted(values)
        assert len(values) == len(set(values))
        assert fake.calls == 3  # 130 nonces => 3 reserves with block size 64

    asyncio.run(_run())


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
