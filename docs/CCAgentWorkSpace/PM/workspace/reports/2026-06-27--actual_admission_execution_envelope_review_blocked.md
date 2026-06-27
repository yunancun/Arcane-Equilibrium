# Actual-Admission Execution Envelope Review Blocked

- Status: `BLOCKED_BY_LOSS_CONTROL`
- Transition: `BLOCKED_BY_LOSS_CONTROL`
- Source/runtime head: `735511d22c9787ee1d90aff9ae3aad3aa175a0ca`
- Candidate: `grid_trading|AVAXUSDT|Sell`

## Summary

The GUI risk semantics remain authoritative: GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`; GUI `Max Single Position=25%` resolves from accepted Demo equity.

This checkpoint added machine-checkable consumption of actual-admission active-window evidence to the current-candidate bounded Demo admission review. The review can now verify public-only actual BBO freshness, released Demo Decision Lease, nested Decision Lease / Guardian evidence, GUI cap lineage, and exact order-shape match while keeping `runtime_admission_ready=false` and `order_admission_ready=false`.

Runtime review failed closed:

- Fresh actual-admission BBO is valid and under GUI cap: `146.4 AVAX / 954.8208 USDT` under `955.1369426 USDT`.
- Nested active Guardian gate used a different order shape: `146.5 AVAX / 955.0335 USDT`.
- Existing timestamped bounded auth object is no longer fresh under the default 6h artifact freshness gate.

No order was submitted. No private Bybit endpoint, PG write, live/mainnet authority, Cost Gate change, writer/adapter enablement, persistent lease, execution, or profit proof occurred.

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_bounded_demo_admission_envelope_review.py`
  - Adds optional `--actual-admission-bbo-window-json`.
  - Validates actual-admission active-window evidence without treating public quote calls or lease acquire/release as order authority.
  - Requires exact actual BBO order shape to match the active-window Guardian gate order shape.
  - Keeps review output no-order: `runtime_admission_ready=false`, `order_admission_ready=false`.
- `helper_scripts/research/tests/test_current_candidate_bounded_demo_admission_envelope_review.py`
  - Covers valid exact-shape actual-admission evidence.
  - Covers exact-shape mismatch fail-closed behavior.
  - Covers authority-contamination rejection if an actual-admission artifact claims order submission.

## Verification

Local:

- Focused bounded admission review: `12 passed`.
- Adjacent admission/actual/gate/sizing suite: `32 passed`.
- Current-candidate helper suite: `63 passed`.
- `py_compile`: passed.
- `git diff --check`: passed.

Runtime:

- Runtime source sync manifest: `/tmp/openclaw/runtime_source_sync_actual_admission_review_20260627T101140Z/runtime_sync_manifest.json`
- Manifest sha: `f3b610e8ec0f9d27b709d3d15583e42392ef60fed54893274d5696036c6b9ff7`
- Runtime focused suite: `32 passed`.
- Runtime current-candidate helper suite: `63 passed`.
- Runtime `py_compile`: passed.
- No service/binary restart; crontab pins updated `8fdc28d7... -> 735511d2...`.

## Runtime Evidence

- Execution-envelope review: `/tmp/openclaw/current_candidate_actual_admission_execution_envelope_review_20260627T101339Z/current_candidate_actual_admission_execution_envelope_review.json`
  - sha `3f1f781874fb5ba04572603eb901c7e827c6cb8609cc894d5b7757514d45826f`
  - status `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`
  - blockers `bounded_demo_authorization_object_valid`, `guardian_risk_gate_valid`, `actual_admission_bbo_window_valid`, `actual_admission_order_shape_matches_guardian_gate`
- Review manifest: `/tmp/openclaw/current_candidate_actual_admission_execution_envelope_review_20260627T101339Z/execution_envelope_review_manifest.json`
  - sha `5bcfa0ab1b350415655d3cf8d450fb50d61ff0c7627257cb43a3c8aae9c57d0a`
- Session loop state: `/tmp/openclaw/session_loop_state_20260627T1013Z_actual_admission_execution_envelope_review_blocked/session_loop_state.json`
  - sha `f4cccf9e63ff5163c6bb589755b5157138a2ca62db98e393c3797c60ce571f60`
- Actual-admission input: `/tmp/openclaw/gui_budget_lineage_actual_admission_preflight_20260627T094933Z/current_candidate_actual_admission_bbo_lease_window_run.json`
  - sha `be9c68ad9ac8d88991753b608859d0758108e0718ba405ffccc73bdf76f567aa`
  - actual BBO `146.4 AVAX / 954.8208 USDT`
  - active gate shape `146.5 AVAX / 955.0335 USDT`

## Next

Refresh a current AVAX bounded auth object only through the standing Demo authorization path if the standing envelope is still valid. Then fix or rerun the final-window actual-admission path so the active Guardian gate evaluates the exact actual BBO order shape, not a stale pre-BBO sizing shape. Do not execute until a fresh same-window lease, BBO, Guardian gate, Rust authority, bounded auth, auditability, and reconstructability all pass simultaneously.
