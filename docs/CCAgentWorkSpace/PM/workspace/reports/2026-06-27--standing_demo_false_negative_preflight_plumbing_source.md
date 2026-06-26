# Standing Demo False-Negative Preflight Plumbing Source

| Field | Value |
|---|---|
| `blocker_id` | `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `local_pre_edit_head` | `fe4f6e448a1aa887a00cce6e88b9e904b9ecc3c3` |
| `runtime_head_before_source_sync` | `69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64` |
| `session_state` | `/tmp/openclaw/session_loop_state_20260626T220507Z_standing_demo_false_negative_preflight_plumbing.json` |
| `smoke_summary` | `/tmp/openclaw/standing_demo_false_negative_preflight_plumbing_smoke_20260626T2255Z/summary.json` |
| `smoke_summary_sha256` | `e639736ac9653861c0e684912f522c64f3801e5e8741cab08a0e157434ab93a8` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-SYNC-REVIEW` |

## Outcome

The false-negative operator review and false-negative bounded-probe preflight layers can now consume a structured `standing_demo_operator_authorization_v1` loss-control envelope. A fresh Demo-only envelope can produce a machine-checkable preflight-ready state, while absent, invalid, stale, live/mainnet-contaminated, or candidate-scope-mismatched envelopes fail closed.

This is source/test plumbing only. It does not emit a bounded operator authorization object, does not enable runtime probe/order authority, and does not lower the Cost Gate.

## Source Changes

- Added `helper_scripts/research/cost_gate_learning_lane/standing_demo_authorization.py` as the shared validator for Demo-only standing envelopes.
- Wired the validator into `false_negative_operator_review.py` and `false_negative_bounded_probe_preflight.py`.
- Kept bounded operator authorization candidate-scoped by reusing the shared validator in `bounded_probe_operator_authorization.py`.
- Added runtime summary/worklist telemetry for standing-envelope validity and approval-source propagation.
- Updated cost-gate and alpha cron wrappers to pass the standing JSON path into false-negative review/preflight stages when explicitly configured.
- Removed the cron auto-authorize pattern: bounded operator authorization now defaults to `defer` even when `STANDING_DEMO_AUTHORIZATION_JSON` exists.

## Smoke Result

Local smoke summary:

```text
review_status=APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT
review_approval_source=standing_demo_authorization
preflight_status=READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION
auth_defer_status=READY_FOR_OPERATOR_AUTHORIZATION_REVIEW
auth_object_emitted=false
active_runtime_probe_authority=false
active_runtime_order_authority=false
```

Artifact hashes from the smoke:

- Review sha: `02f7292320d979759e89dfb2a5f2aa3da7520c0a7cc88cb8157073099b21ba68`
- Preflight sha: `b86aed63f897e7ae0514244e88ebe118207ab32d8dbc6fa3f3150c3528d3f24d`
- Auth defer sha: `cd8087245428cbb41f9a4775d9cb64d8d10ed976a03256a55e1ec9147f595d89`

## Verification

```text
python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/standing_demo_authorization.py helper_scripts/research/cost_gate_learning_lane/false_negative_operator_review.py helper_scripts/research/cost_gate_learning_lane/false_negative_bounded_probe_preflight.py helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/learning_worklist.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py
python3 -m pytest -q --import-mode=importlib helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py
bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/alpha_discovery_throughput_cron.sh
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_false_negative_candidate_friction_scorecard.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py
git diff --check
```

Results:

- py_compile passed.
- False-negative preflight plus bounded auth focused suites: `30 passed`.
- Learning-lane policy suite: `92 passed`.
- Cron static suites: `25 passed`.
- Cron bash syntax passed.
- Adjacent alpha/profitability/candidate-friction suites: `122 passed`.
- Bounded result and execution-realism review suites: `18 passed`.
- `git diff --check` passed.

## Sub-Agent Results

- PA/E1 returned `DONE_WITH_CONCERNS`: recommended shared standing Demo validation and fail-closed gates.
- E2 initially returned a P0 finding that cron auto-switched bounded auth to `authorize` when standing JSON existed. The source was fixed; E2 re-check returned `DONE_WITH_CONCERNS` and confirmed the cron auto-authorize bypass is closed.
- E4 returned `DONE`: ran prioritized tests and found no missing regression surface for the source plumbing.

E2 residual concern: if an operator explicitly sets the bounded auth decision to `authorize`, the previously closed standing Demo authorization path can still use a valid, fresh, candidate-scoped standing envelope as the confirmation source and emit a bounded auth object. This is intentional existing contract from `P0-STANDING-DEMO-AUTHORIZATION-PLUMBING`; scheduled runtime no longer reaches that state from standing JSON presence alone.

## Boundary

No runtime sync was applied in this source checkpoint. No service restart, environment edit, crontab mutation, manual cron run, PG query/write, Bybit/API/order/cancel/modify, Cost Gate lowering, writer/adapter enablement, active probe/order/live authority, or profit/proof claim occurred.

The next actionable blocker is an E3-style runtime sync review for this source commit. Execution evidence remains waiting until runtime has the source, a valid standing envelope is reviewed in runtime context, and bounded Demo loss controls pass.
