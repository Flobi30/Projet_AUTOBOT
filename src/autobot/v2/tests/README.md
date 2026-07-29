# Tests AUTOBOT V2

## Legacy private Kraken API utility — retired

`test_kraken_api.py` and `test-kraken.sh` are historical artefacts. They
previously accessed private Kraken balance/order endpoints and are now
`retired_from_execution`: they fail before reading credentials, constructing a
private client or contacting Kraken.

Do not export API credentials for tests. AUTOBOT's current programme uses:

- public, research-only Kraken collectors for market data;
- hermetic unit and integration tests with mocked private clients where a
  protocol boundary needs coverage;
- the observation-only runtime with paper, live and automatic promotion
  disabled.

Run the supported local suite from the repository root:

```bash
PYTHONPATH=src python -m pytest -q
```

Any future private-exchange integration test requires a separately approved
execution programme. It is out of scope for the current research/shadow work.
