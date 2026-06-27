# Actual BBO Shape Fixed Admission Ready No-Order

- Status: `DONE_WITH_CONCERNS`
- Transition: `DONE_WITH_CONCERNS`
- Source/runtime head: `502463a9b51d3bdc1b9fcd4b2af7750fa19b4dd2`
- Candidate: `grid_trading|AVAXUSDT|Sell`

## Summary

The operator correction remains binding: GUI/Rust RiskConfig is the risk source of truth. GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`; GUI `Max Single Position=25%` is an equity-derived exposure budget.

This checkpoint fixes the final actual-admission evidence chain:

- Fresh Demo equity: `9551.36942603 USDT`.
- GUI P1 10% cap: `955.1369426 USDT`.
- GUI max-single-position 25% budget: `2387.84235651 USDT`.
- Actual BBO order shape: `146.3 AVAX / 954.7538 USDT`.
- Active-window Guardian gate shape: `146.3 AVAX / 954.7538 USDT`.
- Admission review status: `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_READY_NO_ORDER`.

No order was submitted. No Bybit private/order endpoint, PG write, service restart, Cost Gate lowering, risk expansion, live/mainnet authority, persistent lease, fill, PnL, or profit proof occurred.

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_actual_admission_bbo_lease_window.py`
  - Builds active-window gate sizing from the actual BBO construction before evaluating Guardian/Decision Lease gate evidence.
- `helper_scripts/research/cost_gate_learning_lane/current_candidate_decision_lease_guardian_gate_evidence.py`
  - Carries `sizing_source` through risk context for auditability.
- `helper_scripts/research/cost_gate_learning_lane/current_candidate_bounded_demo_admission_envelope_review.py`
  - Prefers `active_window_gate_sizing_proposal` over legacy top-level actual-admission `risk_context` when comparing actual order shape to source sizing.

## Verification

Local:

- Active BBO/gate suite: `43 passed`.
- Bounded admission review focused: `13 passed`.
- Adjacent actual-admission/admission/gate/sizing suite: `44 passed`.
- `py_compile`: passed.
- `git diff --check`: passed.

Runtime:

- Runtime source sync manifest: `/tmp/openclaw/runtime_source_sync_active_bbo_sizing_admission_review_20260627T1045Z/runtime_sync_manifest.json`
- Manifest sha: `aa270dca6f539ef619bacde54f8a9bf43851cd20e09d5646319d445e66f291d3`
- Runtime adjacent suite: `44 passed`.
- Runtime `py_compile`: passed.
- Runtime `git diff --check`: passed.
- No service/binary restart; crontab pins updated to `502463a9b51d3bdc1b9fcd4b2af7750fa19b4dd2`.

## Runtime Evidence

- Equity artifact: `/tmp/openclaw/current_candidate_actual_bbo_shape_fixed_20260627T103729Z/demo_account_equity_artifact_retry.json`
  - sha `ba846084f36b92c2df98791461da47c51a37d7691e139f6b51fb87256e3cec58`
  - status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- No-order envelope: `/tmp/openclaw/current_candidate_actual_bbo_shape_fixed_20260627T103729Z/current_candidate_no_order_refresh_envelope.json`
  - sha `f4b43cc1716eaf998bcabca2ea27bb8ee0d41a7130ad95b1241364a52cbdaf77`
  - status `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`
- Actual-admission BBO window: `/tmp/openclaw/current_candidate_actual_bbo_shape_fixed_20260627T103729Z/current_candidate_actual_admission_bbo_lease_window_run.json`
  - sha `2a3b530e3987b1f92dc3c820f462977211ec12f70258e8a13453f0b28d8ecb6f`
  - status `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER`
- Final bounded admission review: `/tmp/openclaw/current_candidate_actual_bbo_shape_fixed_20260627T103729Z/current_candidate_bounded_demo_admission_envelope_review_after_active_sizing_fix.json`
  - sha `94345bf7257abfe454ee9c1a24f02ff215cb353d605ccd7695e951340b09d82a`
  - status `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_READY_NO_ORDER`
  - failed gates `[]`
  - runtime blockers `[]`
- Session loop state: `/tmp/openclaw/session_loop_state_20260627T1047Z_active_bbo_sizing_admission_ready/session_loop_state.json`
  - sha `4d49c80da88da76e522d7a6bf834a9c2ce31f3209d9d151b19921a4571bb1ee3`
  - status `DONE_WITH_CONCERNS`

## Next

The next step is a separately bounded Demo order-capable runtime invocation that revalidates this envelope in a fresh same-window Decision Lease / actual BBO / Guardian / Rust authority context and records reconstructable fill, fee, slippage, control, and outcome evidence. Stop on any candidate, risk, Guardian, lease, book-clean, auditability, or authority drift.
