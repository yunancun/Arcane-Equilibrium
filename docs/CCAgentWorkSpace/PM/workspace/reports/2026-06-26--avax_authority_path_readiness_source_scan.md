# AVAX Authority Path Readiness Source Scan

Timestamp: 2026-06-26T00:14Z

## Blocker

`P0-BOUNDED-PROBE-AVAX-AUTHORITY-PATH-READINESS-SOURCE-ONLY`

## Decision

DONE. Current Mac source can emit an authority path readiness packet for E3/BB review: `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`.

This is source readiness only. It does not grant runtime admission, adapter enablement, probe authority, order authority, live authority, Cost Gate lowering, or promotion proof.

## Source Change

`bounded_probe_authority_patch_readiness.py` previously failed the existing source seam `order_intent_limit_tif_surface` because the generic source scanner stripped comments/strings and looked only for the concrete `TimeInForce::PostOnly` expression. Current Rust defines `OrderIntent.limit_price`, `OrderIntent.time_in_force`, and `TimeInForce::PostOnly` as an enum variant, so the scan was too narrow.

The scanner now uses a structural check for this seam:

- `OrderIntent` struct body must include `pub limit_price: Option<f64>`.
- `OrderIntent` struct body must include `pub time_in_force: Option<TimeInForce>` or `Option<crate::order_manager::TimeInForce>`.
- `TimeInForce` enum body must include the `PostOnly` variant.

E2 found that a broad `PostOnly` substring check would be fail-open. The final patch includes a synthetic regression where an unrelated enum contains `PostOnly` while `TimeInForce` lacks it; the packet must remain `SOURCE_SCAN_INCOMPLETE`.

## Source-Only Scan Result

Command used `--print-json` only; no runtime `_latest` artifact was overwritten.

Input placement: `/tmp/openclaw/local_touchability_bootstrap_final_20260625T2348Z/outputs/bounded_probe_placement_repair_plan_avax_sell_bootstrap_final_20260625T2348Z.json`

Key output:

- status: `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- reason: `source_contains_required_near_touch_authority_adapter_and_evidence_hooks`
- missing existing seams: `[]`
- missing required seams: `[]`
- runtime/admission propagation status: `RUNTIME_ADMISSION_PROPAGATION_SOURCE_READY_FOR_E3_BB_REVIEW_NO_RUNTIME_AUTHORITY`
- runtime blockers: `runtime_source_sync_not_verified`, `post_restart_pending_order_reconciliation_not_proven`, `runtime_adapter_enablement_not_performed_source_only_packet`
- authority answers remain false: `actual_runtime_admission_enablement_ready=false`, `allowed_to_submit_order_in_current_review=false`, `order_authority_granted=false`, `probe_authority_granted=false`

## Verification

PM local:

- Focused: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py` -> `36 passed`.
- Adjacent: authority readiness, operator authorization, touchability preflight, placement repair, false-negative preflight, and lower-price reroute suites -> `107 passed`.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_authority_patch_readiness.py` -> PASS.
- `git diff --check` -> PASS.

Role chain:

- PA(default): DONE; no design/hard-boundary concerns.
- E2(explorer): PASS after structural scanner fix; no remaining blocking issue.
- E4(worker): DONE; focused `36 passed` twice, bounded-probe family `215 passed` twice, py_compile PASS, diff-check PASS.

## Boundaries

No Bybit call, order, cancel, modify, PG write, `_latest` overwrite, runtime/env/service/crontab mutation, Cost Gate lowering, Rust writer/adapter enablement, probe/order/live authority, or promotion proof occurred.

## Next Blocker

`P0-BOUNDED-PROBE-AVAX-RUNTIME-ADMISSION-E3-BB-REVIEW-DEMO-ONLY`

The next step is review-only PM -> E3 -> BB assessment of the runtime/admission envelope. It must stop before any runtime source sync, service restart, crontab edit, adapter enablement, Bybit order/cancel/modify, PG write, or authority grant unless that exact action is separately approved through the runtime chain.
