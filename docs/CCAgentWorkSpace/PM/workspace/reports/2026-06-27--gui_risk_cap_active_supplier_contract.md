# GUI Risk Cap Active Supplier Contract

## Conclusion

State transition: `BLOCKED_BY_RUNTIME`.

The operator correction is enforced at the active-caller boundary: GUI `P1 Risk/Trade=10.0%` is `per_trade_risk_pct=0.1`, not a fixed `10 USDT` single-order cap. Runtime active-order supplier readiness now requires GUI/Rust RiskConfig percent fields, accepted Demo equity, effective single-order cap, active Decision Lease, candidate-bound order id, and BBO-derived placement. A bare `Some(active_order_request)` or hardcoded local `10.0` cap fails closed.

## Source Change

- Source commit: `a1b19a82460f1e4febdc5a7c62c117af996a4c6e`
- Updated `helper_scripts/research/cost_gate_learning_lane/bounded_probe_authority_patch_readiness.py`.
- Added supplier contract checks for:
  - `ActiveBoundedProbeOrderRequest` construction
  - `ActiveBoundedProbeRiskLimits` construction
  - candidate-bound `bounded_probe_order_link_id_for_candidate`
  - `decision_lease_id`
  - `RiskConfig` / `risk_config` source
  - `per_trade_risk_pct`, `position_size_max_pct`, `max_order_notional_usdt`
  - accepted Demo equity
  - `effective_single_order_cap_usdt` / budget lineage
  - absence of hardcoded local `10 USDT` and default zero cap supplier limits

## Runtime Evidence

- Runtime source synced to `a1b19a82460f1e4febdc5a7c62c117af996a4c6e`.
- Runtime sync manifest: `/tmp/openclaw/rt_sync_gui_supplier_contract_111443Z/runtime_sync_manifest.json`
  - sha256 `dfd9e08835f3de801979d24a98c197daf216e51c9b303a5bd38610772a33fd9a`
  - crontab old `b26dc76e...` occurrences `0`
  - crontab new `a1b19a82...` occurrences `11`
  - line count `70`
  - no service/binary restart
- Natural runtime placement plan latest: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_placement_repair_plan_latest.json`
  - sha256 `70524e0abfadd8207ff9e8edb4da83fae94b198fb407b0e404aba43d579f93cf`
  - candidate `grid_trading|AVAXUSDT|Sell`
  - `max_demo_notional_usdt_per_order=955.1369426`
- Runtime readiness artifact: `/tmp/openclaw/gui_risk_cap_active_supplier_contract_20260627T111522Z/bounded_probe_authority_patch_readiness_gui_contract_runtime.json`
  - sha256 `47017497fd5c35a1b877b9d7302968ac73971dae2aecde512740c22990f622d6`
  - `status=AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
  - `active_order_submission_ready=true`
  - `active_caller_source_ready_for_review=false`
  - `runtime_active_order_request_supplier_present=false`
  - `runtime_active_order_request_supplier_argument_present=false`
  - `suspicious_hardcoded_local_10_usdt_cap_matches=[]`
- Session state: `/tmp/openclaw/gui_risk_cap_active_supplier_contract_20260627T111522Z/session_loop_state.json`
  - sha256 `05094633efd7a8eaa8e5b53b3152bf50d3b17f4659eee2ac784cbf087cf76dc9`
  - `status=BLOCKED_BY_RUNTIME`

## Verification

- Local focused scanner: `37 passed`
- Local adjacent GUI-cap/supplier suite: `87 passed`
- Runtime adjacent GUI-cap/supplier suite: `87 passed`
- `python3 -m py_compile ...bounded_probe_authority_patch_readiness.py ...test_cost_gate_bounded_probe_authority_patch_readiness.py`: passed locally and on runtime
- `git diff --check`: passed locally and on runtime
- Runtime API/watchdog remained active; no service restart.

## Boundary

No order/cancel/modify, no Bybit private/order call, no PG write, no service restart, no Cost Gate lowering, no risk expansion, no writer/adapter enablement, no live/mainnet action, and no profit proof.

Next action: implement or explicitly review the runtime active-order request supplier. It must derive its single-order envelope from GUI/Rust RiskConfig plus accepted Demo equity, not from local `cap_usdt=10`, before any order-capable Demo invocation.
