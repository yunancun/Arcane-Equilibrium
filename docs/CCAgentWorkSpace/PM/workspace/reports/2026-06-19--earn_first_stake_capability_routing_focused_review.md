# Earn First-Stake Capability Routing Focused Review

Date: 2026-06-19
Owner: PM
Verdict: PASS_WITH_LIMITS

## Scope

This is a PM-local focused review for `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME`.
It refreshes source-routing and regression evidence only. It does not close the
runtime/first-stake row.

## Source Review

- `event_consumer/bootstrap.rs` wires Earn capabilities into each `TickPipeline`
  from existing runtime handles: `shared_client` -> `BybitEarnClient`, and
  `audit_pool` -> `EarnMovementWriter`.
- The bootstrap wiring is capability injection only. Constructing those wrapper
  handles does not call Bybit or PG; missing handles keep Gate E-0 fail-closed.
- `IntentProcessor` stores both Earn dependencies as `Option<Arc<_>>`;
  `process_earn_intent` clones them into `dispatch_earn_intent`, where missing
  dependencies reject with `earn_dispatch_unwired`.
- Rust IPC registers `process_earn_intent` as mutating with no IPC global slot,
  dispatches it into `PipelineCommand::ProcessEarnIntent`, and the event-consumer
  owner task calls `IntentProcessor::process_earn_intent`.
- Python `/api/v1/earn/stake` sends `engine="live"` in the IPC params, so the
  operator/live_reserved asset-movement lane does not rely on primary-pipeline
  fallback.

## Verification

Passed:

- `cargo test -p openclaw_engine process_earn_intent_command --lib` - 2 passed
- `cargo test -p openclaw_engine process_earn_intent --lib` - 4 passed
- `cargo test -p openclaw_engine earn_router_fail_closed_when_unwired --lib` - 1 passed
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_earn_routes.py` - 28 passed, 1 existing Pydantic deprecation warning
- `cargo clippy -p openclaw_engine --lib -- -D warnings` - PASS

## Boundary

No real Bybit call, no credential/key/secret mutation, no runtime DB write, no
deploy/rebuild/restart, no auth/risk/order/trading mutation, and no first real
stake evidence was produced.

`P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` remains active. Remaining gates:

- OP-1 Bybit key update / endpoint correction
- OP-2 Earn variant decision
- OP-3 first 100-200 USDT Flexible stake
- review/deploy/restart before runtime can load this source
- first real stake evidence in `learning.earn_movement_log`
