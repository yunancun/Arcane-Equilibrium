# Bounded Probe Authority Patch Readiness

## Summary

- Added source commit `a215323c`: `bounded_demo_probe_authority_patch_readiness_v1`.
- The artifact consumes the existing no-authority `bounded_demo_probe_placement_repair_plan_v1` and statically scans Rust source for the authority-path seams required before an operator-reviewed bounded Demo patch.
- Canonical Linux smoke returned `RUST_PATCH_REQUIRED_NEAR_TOUCH_PLACEMENT_ADAPTER_MISSING`, which is the expected conservative result.

## PM Read

The current design has the right high-level Module and Interface shape for Cost Gate learning, but not enough Depth in the authority path to create profitable learning evidence. The existing Seam records and reviews blocked signals; the missing Implementation is a Rust near-touch Adapter that makes selected Demo attempts touchable while preserving maker-only, bounded, fail-closed behavior.

Profitability path:

1. Do not globally lower Cost Gate.
2. Use side-cell/horizon ranking to concentrate on blocked signals with positive net-cost cushion.
3. Add the Rust authority-path Adapter: fresh BBO, maker-side near-touch PostOnly limit, max initial gap guard, skip-and-record on wide gap, candidate-matched attempt lineage.
4. After separate operator authorization, gather candidate-matched order-to-fill, fill/fee/slippage, matched controls, result-review, and execution-realism evidence.
5. Feed those outcomes back into autonomous learning before any parameter or Cost Gate change.

## Runtime Smoke

- Runtime source: Linux `trade-core` fast-forwarded clean to `a215323c`.
- Input artifact: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_placement_repair_plan_latest.json`.
- Input generated: `2026-06-22T19:16:17.036836+00:00`.
- Smoke generated: `2026-06-22T19:31:48.869675+00:00`.
- Output: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_authority_patch_readiness_latest.{json,md}`.
- Status: `RUST_PATCH_REQUIRED_NEAR_TOUCH_PLACEMENT_ADAPTER_MISSING`.
- Existing authority seams present: `true`.
- Required patch seams present: `false`.
- Probe/order authority granted: `false` / `false`.

## Missing Required Seams

- `near_touch_or_skip_adapter_missing_from_rust_authority_path`
- `fresh_bbo_age_guard_missing_from_rust_authority_path`
- `initial_touch_gap_guard_missing_from_rust_authority_path`
- `touchability_skip_record_missing_from_rust_authority_path`
- `candidate_matched_attempt_lineage_missing_from_rust_authority_path`

## Verification

- Mac `py_compile`: passed.
- Mac focused readiness tests: `6 passed`.
- Mac related bounded-probe suite: `17 passed`.
- Linux `py_compile`: passed.
- Linux related bounded-probe suite: `17 passed`.
- CI was not run.

## Boundary

Source/test/docs + Linux source sync + canonical `/tmp/openclaw` artifact-only smoke only. No PG query/write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
