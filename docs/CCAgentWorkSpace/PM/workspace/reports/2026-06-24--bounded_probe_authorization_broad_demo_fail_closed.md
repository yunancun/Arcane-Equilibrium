# Bounded Probe Authorization Broad Demo Fail-Closed

Date: 2026-06-24  
Blocker: `P0-BOUNDED-PROBE-AUTHORIZATION`  
Candidate: `grid_trading|AVAXUSDT|Sell`  
Scope: authorization review artifact only

## Summary

Fresh runtime artifacts after the API service cutover show the selected false-negative candidate is ready for bounded Demo probe authorization review, but the operator's broad Demo/API operational authorization was not converted into candidate-scoped bounded probe/order authority.

The authorization helper requires an exact typed-confirm phrase. PM did not fabricate that phrase.

Result: `BLOCKED_BY_OPERATOR_ACTION` on exact typed-confirm.

## Fresh Evidence

Runtime artifact timestamps were refreshed around `2026-06-24T13:30+02`:

- `false_negative_bounded_probe_preflight_latest.json`: `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
- `bounded_probe_touchability_preflight_latest.json`: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- `bounded_probe_placement_repair_plan_latest.json`: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- `bounded_probe_authority_patch_readiness_latest.json`: `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- `bounded_probe_operator_authorization_latest.json`: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`

Candidate alignment:

- strategy: `grid_trading`
- symbol: `AVAXUSDT`
- side: `Sell`
- horizon: `60m`

Authority/proof answers in the latest artifacts remained false:

- no global Cost Gate lowering
- no probe authority
- no order authority
- no live authority
- no promotion evidence
- no PG write
- no Bybit call
- no runtime plan mutation

## Structured Attempt

PM generated a non-latest structured attempt to record the current authorization state:

`/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_structured_attempt_broad_demo_session_20260624T1145Z.json`

Inputs:

- decision: `authorize`
- operator id: `ncyu_broad_demo_session_authorization_current_message_not_exact_confirm`
- authorization id: `bdp-grid-avax-sell-broad-demo-session-20260624T1145Z`
- max authorized probe orders requested: `1`
- typed confirm: omitted

Output:

- status: `TYPED_CONFIRM_REQUIRED`
- reason: `typed_confirm_matches`
- blocking gates: `["typed_confirm_matches"]`
- expected typed confirm:
  `authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:1:bdp-grid-avax-sell-broad-demo-session-20260624T1145Z`
- typed confirm provided: `false`
- typed confirm matches: `false`
- `operator_authorization`: `null`
- `operator_authorization_object_emitted`: `false`

## Decision

This is the correct fail-closed result.

Broad Demo/API operational authorization is enough to perform operational and review work, but it is not the same as a candidate-scoped bounded probe authorization object. The exact typed-confirm gate prevents accidental conversion of broad operational language into order/probe authority.

## Anti-Repeat State

`P0-BOUNDED-PROBE-AUTHORIZATION` has now produced the same effective blocker through prior exact-confirm review and this fresh broad-authorization structured attempt.

Do not repeat another read-only authorization audit unless the exact typed-confirm string is new evidence.

## Aggressive Profit Hypotheses

1. False-negative bounded probe for `grid_trading|AVAXUSDT|Sell`
   - why it might make money: strong blocked-after-cost net cushion in prior Cost Gate false-negative evidence
   - fastest safe test: one candidate-scoped bounded Demo probe after exact typed-confirm
   - required data: candidate-matched order, fill, fee, slippage, and matched blocked controls
   - failure condition: no candidate-matched fill, negative net after fees/slippage, or execution realism failure
   - authority required: exact bounded Demo probe authorization only
   - max safe next action: wait for exact typed-confirm or work on source-only execution realism tooling

2. Near-touch-or-skip maker placement
   - why it might make money: improves touchability while preserving maker-fee economics
   - fastest safe test: no-authority shadow/preview or one authorized bounded Demo order
   - required data: BBO age, initial passive gap, post-only result, fill/no-fill lineage
   - failure condition: taker conversion, stale BBO, or no fills after near-touch repair
   - authority required: bounded Demo order/probe authority for real order
   - max safe next action: source-only placement/result review

3. MM current-fee repeat-window path
   - why it might make money: SOXLUSDT current-fee-positive cell already clears current diagnostic fee in one window
   - fastest safe test: independent-window replay/refresh without authority
   - required data: same candidate key across independent windows, OOS/walk-forward, maker execution realism
   - failure condition: repeat window fails or train/holdout divergence
   - authority required: none for replay/artifact work
   - max safe next action: source-only independent-window confirmation

## Status

`BLOCKED_BY_OPERATOR_ACTION`

Next blocker should be source-only/runtime hygiene work, not another authorization audit, unless the exact typed-confirm string is supplied.
