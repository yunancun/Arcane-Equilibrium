# Bounded Probe Active Order Rust Source Patch

- Date: 2026-06-25
- Blocker: `P0-BOUNDED-PROBE-ACTIVE-ORDER-WIRING-RUST-SOURCE-PATCH-DEMO-ONLY`
- Status: `DONE_WITH_CONCERNS`
- Next blocker: `P0-BOUNDED-PROBE-ACTIVE-ORDER-WIRING-E3-BB-REVIEW-DEMO-ONLY`

## Result

The source-only Rust active-order contract is now machine-checkable and ready
for E3/BB exchange-facing review.

Implemented:

- Added `rust/openclaw_engine/src/bounded_probe_active_order.rs`.
- Added candidate-matched active bounded Demo order draft construction.
- Enforced demo/live_demo, `10 USDT` default max notional, one admitted order
  attempt, post-only limit near-touch envelope, normal risk state, no Cost Gate
  adjustment, Rust admission authority, and mandatory `decision_lease_id`.
- Preserved reconstructable lineage hooks: `side_cell_key`, `context_id`,
  `signal_id`, `bounded_probe_attempt`, `order_id`, `order_link_id`, `fill_id`,
  `fee` / `exec_fee`, `slippage_bps`, and `matched_blocked_control`.
- Added dormant writer and dispatch helpers. They are not called by the live
  tick flow and do not enable runtime order authority.
- Hardened source scanners to ignore `#[cfg(test)]` Rust tokens and report
  `runtime_writer_default_adapter_disabled=true`.

## Boundary

No runtime sync, Bybit call, order/cancel/modify, PG write, ledger append,
canonical plan/latest mutation, service/env/crontab mutation, Rust writer
enablement, global Cost Gate lowering, live/mainnet authority, active
probe/order authority, or promotion proof was performed.

`ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW` means source contract
ready for review only. Runtime writer default remains adapter-disabled.

## Verification

- PA/E1 recheck: `PASS`
- E2 recheck: `PASS`
- E4 review: `PASS`; non-blocking Decision Lease and cap concerns were fixed.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_active_order_wiring_contract.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py`: `40 passed`
- `cargo test -p openclaw_engine bounded_probe_active_order --lib`: `4 passed`
- `cargo test -p openclaw_engine writer_active_order_helper_requires_runtime_adapter_enabled --lib`: `1 passed`
- `cargo test -p openclaw_engine active_bounded_probe_submission --lib`: `2 passed`
- `python3 -m py_compile` for active-order/readiness helpers: `PASS`
- Contract smoke: `ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW`, `ACTIVE_ORDER_SUBMISSION_WIRING_PRESENT`, `runtime_writer_default_adapter_disabled=true`, `active_runtime_order_authority=false`, `order_submission_performed=false`
- `git diff --check`: `PASS`

## Concerns

- The next step is E3/BB source/envelope review before any runtime admission or
  exchange-facing action.
- The source is ready for review, but runtime remains inactive by design.
