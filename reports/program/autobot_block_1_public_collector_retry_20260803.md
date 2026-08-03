# AUTOBOT — Block 1 public collector retry hardening — 2026-08-03

## Decision

`GO_RESEARCH_COLLECTION_ONLY`.

The daily public funding refresh had failed twice after a transient Kraken
Futures HTTPS timeout.  The failure remained visible but prevented the data
plane from recovering until the next timer tick.

## Delivered

- The public Kraken Futures client now performs at most two extra attempts
  after an initial transient network, timeout, throttling or 5xx failure.
- Backoff is exponential, bounded and configurable; the scheduled collector
  explicitly uses a one-second initial delay.
- Invalid client requests, malformed responses and persistent failures are not
  retried indefinitely and still fail the systemd job visibly.
- The job retains its public-only endpoint allow-list, read-only container
  root, capability drop, no secret mount and research-data-only write mount.

## Verification

- Focused public collector, CLI, deployment-boundary and public-boundary
  suite: `88 passed`.
- Full regression suite: `2107 passed, 6 skipped, 2 deselected`.
- Python compilation, shell syntax validation and `git diff --check` passed.
- Regression coverage proves transient timeout recovery, no retry for HTTP
  400, bounds validation and the explicit systemd arguments.

## Safety

- No private Kraken endpoint, credential, runtime database or order path is
  available to the collector.
- No strategy, paper capital, live flag, promotion, sizing or leverage changed.
- A persistent collection failure remains a data-quality incident; it never
  turns into fabricated data or an execution authorization.
