# Standing Demo Authorization Refresh Guardrail

Date: 2026-06-30
Status: `DONE_WITH_CONCERNS`
Active blocker closed: `P0-CURRENT-CANDIDATE-STANDING-AUTH-REFRESH-GUARDRAIL`
Next blocker: `P0-CURRENT-CANDIDATE-DOWNSTREAM-BOUNDED-AUTH-ADMISSION-REFRESH`

## Session Loop State

- `session_goal`: Profit-first local multi-agent auto trading bot autonomy loop, Demo-only, auditable, reconstructable, and constrained by survival/loss-control/authorization/Rust authority/Decision Lease boundaries.
- `active_blocker_id`: `P0-CURRENT-CANDIDATE-STANDING-AUTH-REFRESH-GUARDRAIL`.
- `blocker_goal`: Refresh or fail-close the expired current-candidate standing Demo authorization without granting order/probe/live authority.
- `profit_relevance`: Required prerequisite for future candidate-matched Demo fills; no PnL/proof claim is made.
- `source_head`: local/source history includes guardrail source commit `04ec9c55d73226149c2221df51d7ab1881abf796`; latest `origin/main` observed after another checkpoint was `29610b79e3208ba0b9c723233a09b43ddde12779`.
- `runtime_timestamp`: runtime refresh window `2026-06-30T20:52Z` through `2026-06-30T21:02Z`.
- `artifact_mtimes`: fresh equity artifact mtime `2026-06-30T21:01:51.590537+00:00`; materialized standing auth mtime `2026-06-30T21:02:55.431759+00:00`.
- `previous_evidence_checked`: expired standing auth sha `8df714a98f0d193f239a4c35b584870275fd14429ed60be8bc6b4cc22db16acc`, connector readiness sha `e4cad1336db37d08bfdaa2598948908a5b8baa15d75bf9fe8eb6d842e8c1ddee`, settings GET sha `1f25e50709259e4d71fb78f46704d509dac14722513b7b39980e0e3091eae311`, strict order/fill scan sha `83c8a2549278d869137241cd30d4d4068ffcd3f5c01bd0c51379e313f655de1b`.
- `new_evidence_delta_found`: standing auth refreshed and validated; connector readiness still green; no candidate-matched fill evidence.
- `operator_action_required`: `false` for this checkpoint.
- `acceptance_criteria`: source guardrail + tests, runtime refresh review, atomic materialization, post-refresh validator, post-refresh readiness, TODO/report sync, no authority boundary violation.
- `next_blocker_id`: `P0-CURRENT-CANDIDATE-DOWNSTREAM-BOUNDED-AUTH-ADMISSION-REFRESH`.

Session state artifact: `/tmp/openclaw/session_loop_state_20260630T2052Z_standing_auth_refresh_guardrail/session_loop_state.json`, sha `950351d7d038edbd7c1bdc6e4fe5f75997d361821c9ec51b3cf06d642f5d23b9`.

## Work Completed

Source commit `04ec9c55d73226149c2221df51d7ab1881abf796` added `helper_scripts/research/cost_gate_learning_lane/standing_demo_authorization_refresh_guardrail.py`, focused tests, and SCRIPT_INDEX coverage.

The guardrail consumes:

- existing standing Demo auth,
- bounded Demo runtime readiness,
- fresh Demo equity artifact,
- GUI/Rust RiskConfig TOML.

It fail-closes on candidate mismatch, stale equity, authority contamination, probe-order expansion, invalid readiness, or risk-cap expansion. It emits a preview envelope only when the refreshed cap is no larger than the prior standing cap.

Runtime artifacts:

- Fresh Demo equity: `/tmp/openclaw/standing_demo_auth_refresh_guardrail_20260630T2052Z/demo_account_equity_artifact.json`, sha `e3f430d61ddeacaa150654676feeb5c152cb566286a267972217912cad4b0bde`, equity `9541.87597769`, status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`.
- Guardrail review: `/tmp/openclaw/standing_demo_auth_refresh_guardrail_20260630T2052Z/standing_demo_authorization_refresh_guardrail.json`, sha `38a5bf91baff4fc471e898b8ee8c6b04919dd0b8e8a8b00572a01dee17df5e99`, status `STANDING_DEMO_AUTHORIZATION_REFRESH_READY_NO_RUNTIME_MUTATION`.
- Materialization summary: `/tmp/openclaw/standing_demo_auth_refresh_guardrail_20260630T2052Z/standing_demo_authorization_refresh_materialization_summary.json`, sha `178a46550329a9f1a4bdc5152b182620eb6f2b4263eb614c9f36dbcb099f8917`, status `STANDING_DEMO_AUTHORIZATION_REFRESH_MATERIALIZED_NO_ORDER_AUTHORITY`.
- Current materialized standing auth: `/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`, sha `a26666e71462b2fb6d11b1eedbdb9006e6b549393719e1e6933c4f348da3e4d3`, expiry `2026-07-01T09:02:17.250395+00:00`, mode `0600`, max probe orders `2`, refreshed cap `954.18759777 USDT`.
- Post-refresh validator: `/tmp/openclaw/standing_demo_auth_refresh_guardrail_20260630T2052Z/standing_demo_authorization_post_refresh_validator.json`, sha `8dce62a676c3c5370579fd1e2687b0e9c0a64af7fa095e91fb6504cfc820c944`, valid `true`.
- Readiness after refresh: `/tmp/openclaw/standing_demo_auth_refresh_guardrail_20260630T2052Z/bounded_demo_runtime_readiness_after_standing_auth_refresh.json`, sha `ee46a2ae8f84acdb1ebcd7c50ca50de59f76c1a2ae1535d12907dda073a2e1ac`, status `BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES`.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m py_compile ...` passed.
- Focused guardrail tests: `6 passed`.
- Adjacent auth/equity/no-order suite: `52 passed in 0.42s`.
- `git diff --check` passed for the source checkpoint.
- Runtime post-refresh standing auth validator passed.
- Runtime post-refresh bounded Demo readiness remained green.
- Runtime API/watchdog services were active after the checkpoint.

## Dispatch And Boundary

PM handled the source and runtime-state sync. E3 loss-control criteria were applied as a local checklist because this was a bounded Demo standing-envelope refresh and did not submit/cancel/modify orders. BB was skipped because no exchange-facing Bybit/private/order action was performed.

No live/mainnet authority, Decision Lease, active runtime probe/order authority, Bybit private/order call, service/env/crontab mutation, Cost Gate lowering, model/registry mutation, promotion proof, or profitability proof occurred.

## Concerns

The standing auth refresh reduced the effective cap from prior standing cap `954.52067901 USDT` to `954.18759777 USDT`. Historical bounded auth, plan inclusion, and final-window order-shape evidence must not be consumed. The next checkpoint must rebuild bounded auth / plan inclusion / final-window BBO / Decision Lease / Guardian / Rust authority / GUI cap / auditability / reconstructability under the refreshed cap before any bounded Demo order-capable action.
