# GUI Budget Lineage Actual-Admission No-Order Window

- Status: `DONE_WITH_CONCERNS`
- Transition: `DONE_WITH_CONCERNS`
- Source/runtime head: `c13fbce2089264374a1c7ec5a7a1f08bb8dc3b53`
- Candidate: `grid_trading|AVAXUSDT|Sell`

## Summary

Fixed the source gap that let `current_candidate_actual_admission_bbo_lease_window.py` fail closed on `per_trade_budget_usdt_mismatch_gate_packet`: Guardian-adjusted sizing and Decision Lease / Guardian gate evidence now carry full GUI-derived budget lineage.

The operator-corrected semantics are now machine-checkable through the no-order admission chain:

- GUI `P1 Risk/Trade=10.0%` -> `per_trade_risk_pct=0.1` -> `per_trade_budget_usdt=955.1369426`.
- GUI `Max Single Position=25%` -> `single_position_budget_usdt=2387.84235651`.
- `max_order_notional_usdt=0.0` remains disabled, not a fixed local cap.
- Local `10 USDT` bounded diagnostics are not runtime risk authority.

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_guardian_adjusted_sizing_proposal.py`
  - Adds `per_trade_budget_usdt` and `max_order_notional_usdt` to sizing `risk_context`.
  - Preserves zero-valued `max_order_notional_usdt` with explicit first-present parsing.
  - Verifies supplied per-trade budget equals equity times GUI percent when present.
- `helper_scripts/research/cost_gate_learning_lane/current_candidate_decision_lease_guardian_gate_evidence.py`
  - Propagates sizing/admission budget lineage into gate `risk_context`.
  - Adds the same lineage to nested Guardian `risk_limits`.

## Verification

Local:

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q ...` focused GUI/admission suite: `48 passed`.
- `python3 -m py_compile ...` for related helpers: passed.
- `git diff --check`: passed.

Runtime:

- Runtime source sync manifest: `/tmp/openclaw/runtime_source_sync_gui_budget_lineage_20260627T094444Z/runtime_sync_manifest.json`
- Manifest sha: `5f9a2f8d53565f166f0e7a704083f90d054064dd7bba8d0142114fa3ce9851a9`
- Runtime focused GUI/admission suite: `48 passed`.
- Runtime py_compile: passed.
- No service/binary restart; crontab pins updated `646ab4b6... -> c13fbce2...`.

## Runtime Evidence

- Fresh equity: `/tmp/openclaw/gui_budget_lineage_fresh_envelope_20260627T0950Z/demo_account_equity_artifact_ready.json`
  - sha `779562df4ffa8d0be4c74f267c14dd80ffdd6295f59cd615d3ec3681ad22afca`
  - status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- Fresh no-order envelope: `/tmp/openclaw/gui_budget_lineage_fresh_envelope_20260627T0950Z/current_candidate_no_order_refresh_envelope.json`
  - status `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`
- Runtime chain manifest: `/tmp/openclaw/gui_budget_lineage_actual_admission_preflight_20260627T094933Z/gui_budget_lineage_actual_admission_runtime_chain_manifest.json`
  - sha `97aea4ed710c6d44d5989b81aaa679adb7b959cbb6b588ea4a56f0740a455f10`
  - status `GUI_BUDGET_LINEAGE_ACTUAL_ADMISSION_DONE_NO_ORDER`
- Actual-admission no-order run: `/tmp/openclaw/gui_budget_lineage_actual_admission_preflight_20260627T094933Z/current_candidate_actual_admission_bbo_lease_window_run.json`
  - sha `be9c68ad9ac8d88991753b608859d0758108e0718ba405ffccc73bdf76f567aa`
  - status `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER`
  - BBO age `428.726ms`
  - rounded order preview `146.4 AVAX / 954.8208 USDT`
- Active gate evidence: `/tmp/openclaw/gui_budget_lineage_actual_admission_preflight_20260627T094933Z/active_gate_evidence.json`
  - sha `5c7c0ad03babc1b852a914bcf18b280fa8b4ebcb22cd766d3261bcf5ffed6526`
  - status `CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER`
- Post-run governance snapshot: `/tmp/openclaw/gui_budget_lineage_actual_admission_preflight_20260627T094933Z/post_run_governance_snapshot.json`
  - sha `bc6f44cd71ab552b45ec350b238482164332c637c4b83e7a1b697197b90f82cb`
  - `lease_count=0`, `lease_live_count=0`, Guardian `NORMAL`

## Boundaries

This checkpoint acquired and released a short Demo Decision Lease and captured public market data only.

No order was submitted. No Bybit private/order endpoint, PG write, live/mainnet authority, Cost Gate lowering, runtime config mutation, persistent lease, execution, or profit proof occurred.

Next work is a separate runtime-admission/execution-envelope review before any order-capable bounded probe.
