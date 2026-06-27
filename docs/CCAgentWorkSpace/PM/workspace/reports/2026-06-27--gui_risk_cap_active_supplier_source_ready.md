# 2026-06-27 -- GUI Risk Cap Active Supplier Source Ready

## Summary

State transition: `DONE_WITH_CONCERNS`.

This checkpoint fixes the operator-corrected risk semantics at the Rust active bounded-probe supplier boundary. GUI/Rust RiskConfig is authoritative:

- GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`.
- GUI `Max Single Position=25%` is Rust `position_size_max_pct=25.0`, resolved from accepted Demo equity.
- With accepted Demo equity `9551.36942603`, the current per-trade budget is `955.1369426 USDT`; the max-single-position budget is `2387.84235651 USDT`; `max_order_notional_usdt=0.0` remains disabled.

Source commit `26caf8ec4a5a6cdb58ffed65764b897893497a4c6e` makes the active bounded-probe request supplier derive its cap from GUI/Rust `RiskConfig` and accepted Demo equity. It does not grant runtime/order authority.

## Source Changes

- `rust/openclaw_engine/src/bounded_probe_active_order.rs`
  - Added GUI-derived risk-limit construction.
  - Fails closed on invalid Demo equity, invalid percentages, and invalid caps.
  - Treats optional absolute `max_order_notional_usdt` as active only when positive.

- `rust/openclaw_engine/src/intent_processor/mod.rs`
  - Exposes accepted Demo USDT equity for dispatch-side cap construction.

- `rust/openclaw_engine/src/demo_learning_lane_writer.rs`
  - Carries optional `ActiveBoundedProbeOrderRequest` into runtime admission record construction.

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
  - Builds a request only when qty, `risk_state=NORMAL`, Decision Lease id, accepted Demo equity, GUI-derived cap room, candidate-bound order id, and Submit placement all pass.

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_authority_patch_readiness.py`
  - Reads raw writer source for active-order request call-site arguments while preserving stripped-source contract token checks.

## Verification

- `cargo test -p openclaw_engine bounded_probe_active --manifest-path rust/Cargo.toml`
  - `18 passed`
- `cargo test -p openclaw_engine demo_learning_lane_writer --manifest-path rust/Cargo.toml`
  - `10 passed`
- `python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py`
  - `37 passed`
- Adjacent Python GUI-cap/supplier suite
  - `87 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_authority_patch_readiness.py`
- `git diff --check`

## Artifact

- JSON: `/tmp/openclaw/gui_risk_cap_active_supplier_source_ready_20260627T1134Z/bounded_probe_authority_patch_readiness_source_ready.json`
  - sha256 `49f76f1c45d49ab02ec90e2da172f17d05b60de79cc7c80ee2769c08c3a521ab`
- Markdown: `/tmp/openclaw/gui_risk_cap_active_supplier_source_ready_20260627T1134Z/bounded_probe_authority_patch_readiness_source_ready.md`
  - sha256 `c0eda626f7d2374d91d600c326140277dfab1226f1f28012180859b2711f7041`

Important artifact fields:

- `active_caller_source_ready_for_review=true`
- `runtime_active_order_request_supplier_present=true`
- `runtime_active_order_request_supplier_contract_missing=[]`
- `source_ready_sufficient_for_e3_bb_enablement_review=true`
- `runtime_admission_propagation_ready_for_e3_bb_review=true`
- `allowed_to_submit_order=false`
- `runtime_source_sync_verified=false`
- `runtime_adapter_enablement_performed=false`
- `order_submission_performed=false`

The artifact top-level status is `PLACEMENT_REPAIR_PLAN_REQUIRED` because this source-readiness scan did not include a fresh placement plan. That does not invalidate the source supplier evidence; it blocks runtime enablement until placement evidence is refreshed.

## Runtime Status

Runtime source remains last verified at `a1b19a82460f1e4febdc5a7c62c117af996a4c6e`.

The current desktop environment cannot access `/home/ncyu/BybitOpenClaw/srv`, so this checkpoint did not perform runtime source sync, crontab pin update, service restart, runtime readiness probe, writer enablement, adapter enablement, or order-capable invocation.

## Boundaries

No Bybit private/order call, no PG read/write, no service/env/crontab/runtime mutation, no Cost Gate lowering, no risk expansion, no writer/adapter enablement, no live/mainnet action, no order/cancel/modify, no execution, no fill, no PnL, and no profit proof occurred.

## Next Blocker

Proceed only through a reviewed runtime sync/readiness step:

1. ff-only sync runtime to source `26caf8ec...` and verify source/pins.
2. Refresh fresh placement plan evidence.
3. Perform required restart/readiness and pending-order reconciliation checks.
4. Submit source-ready supplier to E3/BB enablement review.
5. Revalidate same-window Decision Lease, Guardian, Rust authority, actual BBO, GUI cap, book cleanliness, auditability, and reconstructability before any Demo order-capable action.
