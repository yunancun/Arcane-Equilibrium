# TODO v186 retCode 110009 semantics source fix

Date: 2026-06-18
Owner: PM-local narrow fix
TODO row: `P2-110009-RETCODE-SEMANTICS-FIX`

## Decision

Bybit V5 official error table currently defines `110009` as:
`The number of stop orders exceeds the maximum allowable limit`.

It is not a PositionNotFound / close-equivalent success code. Treating it as
NoOp can silently swallow a structural stop-order-limit failure. Source now
fails closed.

## Source Changes

- `rust/openclaw_engine/src/bybit_rest_client.rs`
  - `BybitRetCode::PositionNotFound` renamed to `StopOrderLimitExceeded`.
  - `from_code(110009)` now returns `StopOrderLimitExceeded`.
  - The enum helper methods leave 110009 as non-retryable, non-NoOp,
    non-backoff, non-instrument-filter, and non-balance-block.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
  - Removed `110009` from the `110001 => NoOp` family.
  - 110009 now reaches the conservative default `DispatchOutcome::Structural`.
  - Comments around 110017 convergence now explicitly exclude 110009.
- Tests/comments updated in:
  - `rust/openclaw_engine/src/bybit_rest_client_tests.rs`
  - `rust/openclaw_engine/src/event_consumer/dispatch_tests.rs`
  - `rust/openclaw_engine/src/event_consumer/types.rs`
- Reference doc updated:
  - `docs/references/2026-04-04--bybit_api_reference.md`

## Validation

Passed on Mac source checkout:

```bash
cargo test -p openclaw_engine test_bybit_ret_code --lib
cargo test -p openclaw_engine test_classify_stop_order_limit_exceeded_is_structural --lib
cargo test -p openclaw_engine test_classify_110001_noop_110009_structural_no_regression --lib
cargo test -p openclaw_engine test_close_dup_is_idempotent_success_other_retcode_false --lib
cargo test -p openclaw_engine test_send_exchange_zero_close_suppressed_for_110001 --lib
cargo test -p openclaw_engine event_consumer::dispatch::tests --lib
```

Observed results:

- retCode focused tests: 2 passed.
- changed dispatch focused tests: all passed.
- full `event_consumer::dispatch::tests`: 56 passed.

## Dispatch Chain Note

This chain was shortened deliberately and handled PM-local:

- Scope was a small enum/classifier/test drift correction.
- The exchange-side semantic source is the official Bybit V5 error table.
- The user did not request parallel/sub-agent delegation, and the available
  multi-agent tool explicitly forbids unsolicited spawning.

No PA/E1/E2/E4/BB sub-agent was spawned for this narrow source fix.

## Boundary

- No deploy/rebuild/restart.
- Running Linux engine binary is not claimed to include this fix.
- No production runtime, DB, auth, risk, or trading mutation.
- This closes the source TODO row only; runtime uptake remains under the next
  normal deploy gate.
