# Demo Residual Cleanup Action - CSRF Block

Timestamp: 2026-06-26T02:02Z

## Blocker

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW`

## Decision

`BLOCKED_BY_RUNTIME_AUTHORIZATION`.

E3 and BB both approved the demo-only control-plane cleanup envelope in
principle, but the actual control API POST was rejected by CSRF middleware
before the route executed. No exchange mutation occurred. Candidate selection
remains blocked.

## Session State

- `/tmp/openclaw/session_loop_state_20260626T015300Z_demo_residual_exposure_cleanup_action.json`
- `/tmp/openclaw/session_loop_state_packet_20260626T015300Z_demo_residual_exposure_cleanup_action.json`
- Anti-repeat decision: `new_evidence_delta_allows_active_blocker_progress`

## Review Chain

E3: `DONE_WITH_CONCERNS`.

- Allowed exactly one demo-only `POST /api/v1/strategy/demo/session/stop` only
  after a fresh read-only demo inventory and BB approval.
- Required existing auth path with operator role, `paper:trade`, Bearer/cookie
  auth, and CSRF double-submit.
- Stop conditions included auth/CSRF failure.
- Rejected direct Bybit POST shortcuts, standalone protective-stop cancel,
  manual close/cancel scripts, PG writes, source sync/restart, env/crontab
  mutation, Cost Gate change, Rust writer/adapter enablement, and any
  probe/order/live authority.

BB: `DONE_WITH_CONCERNS`.

- Accepted the runtime endpoint sequence for full demo cleanup:
  pause demo dispatch, cancel USDT-linear demo open orders, close tracked
  positions, sweep orphan positions reduce-only, verify clean.
- Concern: canceling protective StopLoss conditionals before position close is
  acceptable only inside this immediate flatten sequence, never as a standalone
  stop-removal action.

## Fresh Evidence

Fresh pre-action cursor-aware Bybit demo inventory:

- Artifact:
  `/tmp/openclaw/audit/bybit_demo_cleanup_action_pre_inventory/20260626T015816Z_pre_inventory.json`
- Generated: `2026-06-26T01:58:16Z`
- Open orders: `5`
- Open-order symbols: `ETCUSDT`, `FILUSDT`, `ICPUSDT`, `INJUSDT`, `NEARUSDT`
- Estimated open notional: `486.24260000 USDT`
- Nonzero positions: `3`
- Position symbols: `FILUSDT`, `ICPUSDT`, `NEARUSDT`
- Position value: `435.14105000 USDT`
- Unrealised PnL: `-18.28692000 USDT`

PG read-only snapshot:

- Timestamp: `2026-06-26 03:52:27.985293+02`
- 72h demo fills: `83`
- Missing `order_id`: `0`
- Missing `context_id`: `0`
- Unattributed or blank `strategy_name`: `3`
- 24h effective Working orders: `2`
  - `oc_dm_1782438000052_112` `ETCUSDT` Buy Limit PostOnly
  - `oc_dm_1782437036355_109` `INJUSDT` Buy Limit PostOnly

Passive healthcheck:

- Timestamp: `2026-06-26T01:50:53Z`
- Summary: `FAIL`
- [68] demo `working_n=2`, resting about `487 USDT`, filled local exposure `0`,
  divergence `48735.0%`
- [74] close-maker reject samples `FAIL`

## Action Attempt

Attempted exactly one control API POST:

- Endpoint path: `/api/v1/strategy/demo/session/stop`
- Host: `100.91.109.86:8000`
- Auth handling: Bearer token loaded from the existing 0600 token file into a
  temporary 0600 curl config; token and CSRF values were not printed.
- Response artifact:
  `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_response.json`
- Meta artifact:
  `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T015900Z_session_stop_meta.json`
- HTTP status: `403`
- Response reason: `csrf_token_mismatch`, missing cookie `oc_csrf`

The route did not execute. Therefore:

- no demo order cancel occurred
- no demo position close occurred
- no direct Bybit POST was used
- no PG write occurred
- no source sync, restart, crontab/env mutation, Cost Gate change, writer,
  adapter, probe/order/live authority, or promotion proof occurred

## State Transition

- `active_blocker_id`:
  `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW`
- `status`: `BLOCKED_BY_RUNTIME_AUTHORIZATION`
- `next_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-API-CSRF-CLI-INVOKER`

`why_not_repeating_current_blocker`: the blocker has new evidence and a
reviewed action envelope. Repeating the prior read-only inventory or
classification would violate anti-repeat. The next executable step is a narrow
runtime-auth/CSRF invocation checkpoint, not another exposure audit.

## Max Safe Next Action

Create a narrow runtime-auth/CSRF invocation checkpoint:

- verify a secret-safe control API cookie delivery path without exchange
  mutation, or use an already authenticated same-origin GUI/session path
- refresh E3/BB approval before any second exchange-facing cleanup POST
- keep candidate selection blocked until post-clean inventory, healthcheck, and
  PG read-only reconciliation prove a clean or explicitly accepted posture

## Aggressive Profit Hypotheses

1. `clean_book_unlock_for_one_bounded_candidate`
   - `why_it_might_make_money`: clean exchange state prevents residual exposure
     and proof-excluded fills from contaminating candidate PnL selection.
   - `fastest_safe_test`: resolve CSRF invocation, execute reviewed cleanup,
     then select exactly one no-authority candidate packet.
   - `required_data`: post-clean inventory, healthcheck [68], PG/fill
     attribution, fee/slippage-aware candidate controls.
   - `failure_condition`: any residual position/order remains unexplained or
     fills are not candidate-attributed.
   - `authority_required`: E3/BB cleanup envelope; bounded-probe authority is
     separate and not granted.
   - scores: expected_net_pnl_upside `5/5`, evidence_strength `4/5`,
     execution_realism `3/5`, cost_after_fees `3/5`, time_to_test `3/5`,
     risk_to_account `2/5`, risk_to_governance `1/5`, autonomy_value `5/5`.
2. `csrf_safe_control_plane_invoker`
   - `why_it_might_make_money`: a reliable, audited invocation path lets demo
     cleanup and future live-applicable risk reduction happen quickly without
     weakening auth.
   - `fastest_safe_test`: source/read-only E3 review of CLI cookie delivery;
     prove on non-exchange path or refresh E3/BB before exchange POST.
   - `required_data`: CSRF middleware behavior, auth path, route classification,
     secret-safe curl config handling.
   - `failure_condition`: token/cookie leaks, dynamic CSRF bypass, or any
     exchange mutation during the auth smoke.
   - `authority_required`: E3; BB only if exchange-facing.
   - scores: expected_net_pnl_upside `3/5`, evidence_strength `5/5`,
     execution_realism `4/5`, cost_after_fees `4/5`, time_to_test `4/5`,
     risk_to_account `1/5`, risk_to_governance `2/5`, autonomy_value `5/5`.
3. `maker_path_after_exposure_cleanup`
   - `why_it_might_make_money`: linked PostOnly entries show passive placement
     works, but edge cannot be assessed until book state and lineage are clean.
   - `fastest_safe_test`: post-clean maker-ratio candidate packet with
     adverse-selection controls.
   - `required_data`: clean inventory, BBO freshness, maker/taker fees, matched
     fills, controls.
   - `failure_condition`: maker fills lack attribution or controls erase the
     edge after fees/slippage.
   - `authority_required`: candidate review first; bounded Demo probe later.
   - scores: expected_net_pnl_upside `4/5`, evidence_strength `3/5`,
     execution_realism `3/5`, cost_after_fees `4/5`, time_to_test `2/5`,
     risk_to_account `2/5`, risk_to_governance `1/5`, autonomy_value `4/5`.

PM SIGN-OFF: `BLOCKED_BY_RUNTIME_AUTHORIZATION`.
