# WebSocket Metrics Hardening - 2026-06-11

## Change

The former repeated `WS backpressure` warning now reports `WS high_message_rate`. The compatibility health field `backpressure_active` remains available, but the new fields make the meaning explicit:

- `messages_per_second`;
- `high_message_rate_active`;
- `high_message_rate_windows`;
- `last_tick_age_seconds`;
- `dispatch_ewma_ms`;
- `exchange_local_lag_ms` when a real exchange timestamp becomes available;
- `explicit_drop_count`;
- `drop_tracking_supported`.

The log is emitted immediately on the first high-rate condition, then at most once every 300 seconds while the state stays high. The interval is configurable through `WS_HIGH_MESSAGE_RATE_LOG_INTERVAL_S` with a minimum of 30 seconds.

## Important distinction

High message rate is not treated as evidence of message loss. The current receive loop has no explicit drop path, so `explicit_drop_count` remains zero. Invalid-book and recovery metrics remain owned by order-flow/orchestrator components and are not mixed with WebSocket rate metrics.

## Runtime behavior preserved

- No subscription changed.
- No callback changed.
- No market message is blocked.
- No queue architecture was introduced.
- No execution, sizing, risk or trading flag changed.

## Validation

The focused test proves rate limiting, preserves the high-rate health state, keeps explicit drops at zero and keeps invalid-book metrics separate.
