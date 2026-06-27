# Current Candidate Standing Demo Loss-Control Envelope Review

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0251Z_current_candidate_standing_demo_loss_control_envelope_review.json` |
| `session_loop_state_sha256` | `b82efd458997b78b45cfb817703b21992dd0bc0abf484c0f48a4072e4bbe573e` |
| `source_head` | `9b0bd6a3150b65d43644ebcc236ea2e8293652c9` |
| `runtime_head` | `665b2eef615cd1d93f0691a757f9ab4c3ade83ed` |

## Decision

新增並執行 current-candidate standing Demo loss-control envelope review。結果是 `CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_READY_NO_RUNTIME_MUTATION`。

這代表 current `grid_trading|AVAXUSDT|Sell` 已有 candidate-scoped `standing_demo_operator_authorization_v1` preview，可提交下一步 runtime materialization review。它不是 bounded authorization object，不是 Decision Lease，不是 Guardian/Rust authority，不是 runtime/order admission，也不是 profit proof。

## Source/Test

新增：

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_standing_demo_loss_control_envelope_review.py`
- `helper_scripts/research/tests/test_current_candidate_standing_demo_loss_control_envelope_review.py`

補：

- `helper_scripts/SCRIPT_INDEX.md`

驗證：

- focused pytest: `5 passed`
- adjacent pytest: `58 passed`
- `py_compile`: pass
- `git diff --check`: pass before source commit

Source/test commit pushed:

- `9b0bd6a3150b65d43644ebcc236ea2e8293652c9`

## Review Artifact

Inputs:

- admission review: `/tmp/openclaw/current_candidate_bounded_demo_admission_envelope_review_20260627T023903Z/current_candidate_bounded_demo_admission_envelope_review.json`, sha `34cd80461706cde2dad8bb5bff9b2d72224230452a2b6d989ee9ae1b6f4b224c`
- current envelope: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/current_candidate_no_order_refresh_envelope.json`, sha `993ff2ca0c027281d81d8fb80a2357b3063c41ecbb9261b8740b7ebc02fef9eb`
- runtime false-negative candidate packet snapshot: sha `d6ad26510c9f41856dfda47d111bac29bcde3bbf13142ad6302f3e054a28af90`

Output:

- path: `/tmp/openclaw/current_candidate_standing_demo_loss_control_envelope_review_20260627T025157Z/current_candidate_standing_demo_loss_control_envelope_review.json`
- sha: `c6970005efab04a9da02ce54b08c60e563e465fbf9c736e9767a3feabc978c03`
- status: `CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_READY_NO_RUNTIME_MUTATION`
- candidate: `grid_trading|AVAXUSDT|Sell`

Proposed standing envelope preview:

- schema: `standing_demo_operator_authorization_v1`
- status: `STANDING_DEMO_AUTHORIZATION_ACTIVE`
- standing id: `standing-demo-current-candidate-20260627T025158Z-d05921ff67d4`
- operator id: `current-candidate-standing-demo-loss-control-review`
- environment: `demo`
- scope: `demo_api_only_bounded_probe`
- max authorized probe orders per candidate: `2`
- TTL: `12h`
- candidate scope: `grid_trading|AVAXUSDT|Sell`
- shared standing validator: `valid_for_candidate_scoped_authorization=true`

Risk lineage preserved:

- GUI/Rust RiskConfig source of truth: true
- GUI P1 risk/trade: `10.0%`
- `per_trade_risk_pct_fraction`: `0.1`
- max single position: `25.0%`
- accepted Demo equity: `9552.43426257`
- resolved cap: `955.24342626 USDT`
- constructed notional: `954.6264 USDT`
- local `10 USDT` as global risk authority: false

Still false:

- `standing_envelope_materialized=false`
- `operator_authorization_object_emitted=false`
- `bounded_demo_probe_authorized=false`
- `decision_lease_emitted=false`
- `runtime_admission_ready=false`
- `order_admission_ready=false`
- `order_submission_performed=false`
- `runtime_mutation_performed=false`
- `global_cost_gate_lowering_recommended=false`

## Boundary

No runtime standing JSON write, no env/crontab mutation, no Bybit call, no private endpoint, no order/cancel/modify, no Control API POST, no PG query/write, no service restart, no Cost Gate lowering, no risk expansion, no bounded auth/probe/order/live authority, and no profit proof.

## Next

Next safe work is a reviewed runtime materialization step for this current-candidate standing envelope preview. After materialization, refresh false-negative review/preflight and bounded authorization review in defer/no-order mode. Do not submit orders until bounded auth object, Decision Lease, Guardian risk gate, Rust authority path, actual-admission fresh BBO, auditability, and reconstructability all pass.
