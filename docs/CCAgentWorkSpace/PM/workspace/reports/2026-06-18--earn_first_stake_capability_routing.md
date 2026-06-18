# Earn First-Stake Capability Routing — PM Checkpoint

Date: 2026-06-18

## Scope

Reduced the remaining source-side blocker inside `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME`.

Changes:
- Rust `event_consumer/bootstrap.rs` now wires Earn capabilities into each pipeline `IntentProcessor` when the existing runtime handles are present:
  - `shared_client` -> `BybitEarnClient`
  - `audit_pool` -> `EarnMovementWriter`
- Python `/api/v1/earn/stake` now sends `engine="live"` in the `process_earn_intent` IPC params, so the operator/live_reserved asset-movement path does not rely on Rust primary-pipeline fallback.
- Rust owner-task regression now proves a wired Live pipeline moves past `earn_dispatch_unwired` and is stopped by governance authorization before any DB/Bybit call.

## Verification

Passed:
- `rustfmt --edition 2021 --check openclaw_engine/src/event_consumer/bootstrap.rs openclaw_engine/src/event_consumer/tests/earn_ipc_tests.rs`
- `cargo test -p openclaw_engine process_earn_intent_command --lib` — 2 passed
- `cargo test -p openclaw_engine process_earn_intent --lib` — 4 passed
- `cargo test -p openclaw_engine earn_router_fail_closed_when_unwired --lib` — 1 passed
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_earn_routes.py` — 28 passed, 1 existing Pydantic deprecation warning
- `git diff --check`

## Boundary

No real Bybit call, no credential/key/secret mutation, no runtime DB mutation, no CI full suite, no deploy/rebuild/restart, and no auth/risk/order/trading mutation.

`P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` remains active. Remaining gates:
- OP-1 Bybit key update
- OP-2 Earn variant decision
- OP-3 first $100-$200 USDT Flexible stake
- review/deploy/restart before runtime can load this source
- first real stake evidence in `learning.earn_movement_log`
