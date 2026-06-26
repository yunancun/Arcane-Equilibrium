# Standing Demo Authorization Plumbing Source Fix

Date: 2026-06-26 23:31 CEST

本輪推進 `P0-STANDING-DEMO-AUTHORIZATION-PLUMBING` 到 source/test/docs `DONE_WITH_CONCERNS`。沒有 runtime sync、沒有 crontab/env/service mutation、沒有 Bybit/API/order/cancel/modify、沒有 PG query/write、沒有 Cost Gate lowering、沒有 writer/adapter enablement、沒有 active probe/order/live authority，也沒有 proof/profit claim。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P0-STANDING-DEMO-AUTHORIZATION-PLUMBING` |
| `blocker_goal` | 讓 runtime refresh chain 能消費 structured standing Demo authorization envelope，而不是只產生 generic `defer`。 |
| `profit_relevance` | 這是 candidate-matched Demo fills、fees/slippage、after-cost PnL review 之前的當前 unlock；它修 autonomy plumbing，不是人工交易決策。 |
| `previous_evidence_checked` | TODO v593；profit-first loop spec；PM reports `todo_source_pointer_drift_correction`、`p0_auth_semantic_delta_noop_no_authority`、`standing_demo_authorization_contract`；runtime auth/review/preflight/profitability artifacts。 |
| `new_evidence_delta_found` | Runtime artifacts at `2026-06-26T21:15:05Z` refreshed hash/mtime but semantic auth remains AVAX Sell `decision=defer`, no `authorization_id`, no runtime probe/order authority。 |
| `action_taken` | Source plumbing fix: standing Demo JSON can now derive candidate-scoped authorization id/budget/expiry; cost-gate and alpha cron wrappers can opt into standing JSON and auto-select `authorize` only when that file exists. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-AUTH-PLUMBING-SYNC-REVIEW` |

## Source Change

Changed:

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py`
- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `helper_scripts/cron/alpha_discovery_throughput_cron.sh`
- cron static tests for both wrappers

Behavior:

- `decision=authorize` + valid `standing_demo_operator_authorization_v1` + no typed confirm now derives a deterministic candidate-scoped `authorization_id`, bounded order budget, and expiry from the standing envelope and source candidate budget.
- Missing standing JSON keeps cron behavior at `defer`.
- Present standing JSON path switches the wrapper decision to `authorize` and passes `--standing-demo-authorization-json`.
- Raw `--operator-id`, `--authorization-id`, and `--typed-confirm` are still not injected by cron.
- Packet answers continue to report `active_runtime_probe_authority=false` and `active_runtime_order_authority=false`; the emitted object is plan-admission input only, not an order submission.

## Local Smoke

Artifact-only smoke:

- path: `/tmp/openclaw/standing_demo_auth_plumbing_smoke_20260626T2115Z/bounded_probe_operator_authorization.json`
- status: `BOUNDED_DEMO_PROBE_AUTHORIZED`
- confirmation source: `standing_demo_authorization`
- derived authorization id prefix: `standing-demo-`
- max authorized probe orders: `2`
- active runtime probe/order authority: `false/false`

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
21 passed

python3 -m pytest -q --import-mode=importlib helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py
24 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_false_negative_candidate_friction_scorecard.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py
140 passed

bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh
PASS

bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh
PASS

python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization_cli.py
PASS

git diff --check
PASS
```

## Concern

Runtime `trade-core` remains at `b224c759200d8dfc6fc4a53cbee39b8fb3683118` for this checkpoint. The next safe action is an E3-reviewed runtime source sync plus expected-head post-checks. No bounded Demo execution should start until runtime is synced, a valid standing envelope is present, and plan/admission/reconciliation gates pass.
