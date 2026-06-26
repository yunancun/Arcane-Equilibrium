# AVAX Touchability Bootstrap Source Patch

Timestamp: 2026-06-25T23:53Z

## Blocker

`P0-BOUNDED-PROBE-AVAX-CANDIDATE-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY`

## Decision

DONE. A zero candidate-matched order state may advance to a first-attempt touchability bootstrap only as a review-only near-touch-or-skip design contract. It does not grant probe/order/live authority, does not mutate runtime state, and is not promotion or bounded-probe proof.

## Source Changes

- `bounded_probe_touchability_preflight.py` emits `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` only when the preflight design is reviewable, candidate identity matches the structured side-cell, fill flow exists only outside the candidate, and `candidate_reviewed_orders == 0`.
- `bounded_probe_placement_repair_plan.py` maps that bootstrap status to `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` with `active=false`, separate authorization required, fresh-BBO/near-touch-or-skip constraints, and `first_attempt_bootstrap_is_proof=false`.
- Both helpers now recursively reject broader authority/mutation/proof contamination keys aligned with adjacent bounded-probe helpers, including `runtime_order_authority_granted`, `runtime_order_authority_found`, `order_authority_granted_in_authorization_object`, `config_mutation_performed`, `env_mutation_performed`, `environment_mutation_performed`, `order_modify_performed`, `review_grants_runtime_authority`, and `cost_gate_mutation_found`. Forbidden-key enum strings such as `ORDER_AUTHORITY_GRANTED` / `DEMO_LEARNING_PROBE_GRANTED` and non-empty object/list payloads fail closed.

## Verification

- Focused: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_touchability_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py` -> `30 passed`.
- Adjacent: same env over touchability, placement, lower-price reroute, operator authorization, authority patch readiness, and false-negative preflight suites -> `106 passed`.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` on changed helpers -> PASS.
- `git diff --check` -> PASS.
- E2 final: PASS after enum/object payloads plus `allowed_to_submit_order_in_current_review` and `actual_runtime_admission_enablement_ready` were added to the recursive scanner coverage.
- E4 final: PASS.

## Existing Clean-Input Smoke

Earlier in this round, clean copied inputs produced `/tmp/openclaw/local_touchability_bootstrap_final_20260625T2348Z/outputs`:

- touchability status `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`.
- placement status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`.
- authority readiness status `SOURCE_SCAN_INCOMPLETE`.
- operator authorization status `AUTHORITY_PATH_PATCH_NOT_READY`.

No new artifact smoke was rerun after the denylist-only fix because clean-input behavior did not change; the new coverage is regression tests for authority contamination.

## Boundaries

No Bybit call, order, cancel, modify, PG write, `_latest` overwrite, runtime/env/service/crontab mutation, Cost Gate lowering, Rust writer/adapter enablement, probe/order/live authority, or promotion proof occurred.

## Next Blocker

`P0-BOUNDED-PROBE-AVAX-AUTHORITY-PATH-READINESS-SOURCE-ONLY`

The next step is source-only authority/readiness scanning. It must either produce a review packet for E3/BB with required Rust/runtime admission seams present, or fail closed with exact missing seams.
