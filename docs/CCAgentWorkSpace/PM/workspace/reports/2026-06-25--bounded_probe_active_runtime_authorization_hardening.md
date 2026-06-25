# PM Report: Bounded Probe Active Runtime Authorization Hardening

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-ACTIVE-RUNTIME-AUTHORIZATION-HARDENING-DEMO-ONLY`

## Decision

Closed the v505 E3/BB caveats as source-level fail-closed constraints. This is still no-authority source hardening: no runtime adapter was enabled, no Bybit call was made, and no order/cancel/modify path was exercised.

## Source Changes

- `rust/openclaw_engine/src/bounded_probe_active_order.rs`
  - Pins active bounded Demo cap to `<= 10 USDT`.
  - Requires local Bybit-safe `orderLinkId` shape `oc_{dm|ld}_{ts_ms}_{seq}` with engine-mode tag match, event timestamp match, max 36 chars, allowed charset, and positive seq.
  - Rejects non-finite/nonpositive placement limit/reference prices.
  - Carries explicit `maker_timeout_ms` in risk limits and order draft.
  - Preserves Decision Lease and candidate/order/fill/fee/slippage lineage hooks.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
  - Dormant dispatch helper now forwards `maker_timeout_ms: Some(draft.maker_timeout_ms)`.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch_tests.rs`
  - Asserts the explicit maker timeout reaches `OrderDispatchRequest`.

## Review Chain

- PA: PASS, design step is appropriate source-only hardening before runtime authorization.
- E1: PASS, no implementation blocker; non-blocking API/coverage concerns were addressed with additional tests where relevant.
- E2: PASS, no blocker; strict orderLinkId shape matches current generator pattern.
- E4: PASS, focused Mac verification passed.

## Verification

- `cargo test -p openclaw_engine bounded_probe_active_order --lib` -> `10 passed`
- `cargo test -p openclaw_engine active_bounded_probe_submission --lib` -> `2 passed`
- `cargo test -p openclaw_engine writer_active_order_helper_requires_runtime_adapter_enabled --lib` -> `1 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_active_order_wiring_contract.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py` -> `40 passed`
- `git diff --check` -> PASS

## Boundary

No runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG read/write, no Bybit API call, no service/env/crontab mutation, no Rust writer enablement, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Next Safe Action

Before any adapter enablement or Demo order authority, run PM->E3->BB runtime authorization review for the actual request-construction caller, seq uniqueness/restart behavior, cancel-by-`orderLinkId`, and fill/fee/slippage reconstructability.
