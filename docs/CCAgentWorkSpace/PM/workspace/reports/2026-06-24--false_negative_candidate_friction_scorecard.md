# False-Negative Candidate Friction Scorecard

Date: 2026-06-24
PM status: `DONE_WITH_CONCERNS`
Source branch / base head: `main` / `b3f183079aece357d015518470ef7a02c4ef5976`

## Session Loop State

- `active_blocker_id`: `P1-AGGRESSIVE-ALPHA-FRICTION-SCORECARD`
- `blocker_goal`: while `P0-BOUNDED-PROBE-AUTHORIZATION` is blocked by exact typed-confirm, create a source-only scorecard that ranks false-negative candidates by profit upside and bounded-probe friction without emitting any authority.
- `profit_relevance`: high. It keeps the loop profit-first by finding the next highest-upside path if the current AVAX bounded authorization remains blocked, while preserving candidate-matched execution proof requirements.
- `completed_blockers`: `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`, `P1-LEARNING-LOOP-CLOSURE`, `P1-AUTONOMOUS-PARAMETER-PROPOSAL`, `P1-RUNTIME-HEALTH-HYGIENE`
- `blocked_blockers`: `P0-BOUNDED-PROBE-AUTHORIZATION`, `P0-PROFIT-OUTCOME-REVIEW`
- `previous_report_paths`: `2026-06-24--bounded_probe_authorization_exact_confirm_gate.md`, `2026-06-24--false_negative_review_approval_durability.md`, `2026-06-24--candidate_matched_touchability_gate.md`
- `source_head`: `b3f183079aece357d015518470ef7a02c4ef5976` before this source-only patch.
- `runtime_timestamp`: `2026-06-24T09:11:37+02:00`
- `pg_snapshot_timestamp`: `2026-06-24 09:11:37.71624+02` via read-only `SELECT now()`.
- `artifact_mtimes`: runtime latest authorization attempt and bounded artifacts were inspected before this source-only patch; Mac local `/tmp/openclaw` smoke intentionally failed closed because runtime artifacts are not present on the Mac.
- `operator_action_required`: false for this source-only scorecard; true remains for any actual bounded Demo probe authorization object.
- `new_evidence_delta_required`: P0 exact-confirm has no new typed-confirm delta, so the loop must not re-run the same authorization attempt. Source-only progress needs a new scope.
- `new_evidence_delta_found`: yes. New source-only scope `false_negative_candidate_friction_scorecard_v1` ranks candidates by edge/friction and tightens fail-closed boundaries.
- `acceptance_criteria`: no global Cost Gate lowering, no live, no Bybit call, no PG write, no crontab/service/runtime mutation, no active runtime order/probe authority, no authorization object, no promotion proof, and no use of this scorecard as bounded-probe authorization.
- `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked by exact typed-confirm; next safe fallback is another source-only aggressive-alpha blocker if no exact-confirm delta appears.

## Anti-Repeat Decision

Decision: `active_blocker_repeatedly_blocked_by_operator_action_then_source_only_progress_allowed`

Reason: the previous P0 authorization attempt already proved the chain is blocked only by exact typed-confirm. Re-running the same read-only authorization audit without a new typed-confirm would violate the anti-repeat rule. This round therefore moved to a distinct source-only aggressive-alpha scope.

## Action Taken

Added `helper_scripts/research/cost_gate_learning_lane/false_negative_candidate_friction_scorecard.py`.

The helper consumes:

- `cost_gate_false_negative_candidate_packet_v1`
- `bounded_demo_probe_touchability_preflight_v1`
- `bounded_demo_probe_placement_repair_plan_v1`
- `bounded_demo_probe_operator_authorization_packet_v1`

It produces `cost_gate_false_negative_candidate_friction_scorecard_v1`, ranking false-negative candidates by:

- wrongful-block edge score
- net cost cushion
- net-positive percentage
- outcome sample strength
- candidate-scoped touchability friction
- candidate-scoped placement friction
- candidate-scoped authorization friction

It fails closed when:

- required artifacts are missing, stale, unknown-age, or schema-mismatched;
- touchability, placement, and authorization active candidates are not aligned;
- a single artifact contains conflicting top-level/nested candidate identities;
- any input carries Cost Gate lowering, probe/order authority, active runtime authority, PG/Bybit/order/runtime mutation, live promotion, or promotion proof/evidence signals.

`TYPED_CONFIRM_REQUIRED` is only surfaced as a next action:

`exact_bounded_demo_typed_confirm_required_or_select_next_candidate`

It does not emit an authorization object and is not consumed by runtime admission.

## Verification

- PA no-edit design review: PASS, with condition that this remains source-only triage and cannot replace exact-confirm.
- E2 first review found two medium findings:
  - `bybit_call_performed=true` was not fail-closed.
  - nested placement candidate mismatch could be hidden by top-level candidate alignment.
- PM fixed both findings with expanded mutation/authority key checks and intra-artifact candidate identity validation.
- E2 re-review: PASS.
- E4 re-review: PASS.
- Mac focused scorecard tests: `9 passed`.
- Mac adjacent bounded helper suite: `60 passed`.
- Mac bounded helper suite including authority patch readiness: `67 passed`.
- Mac alpha/profitability/worklist suite: `108 passed`.
- E4 independent bounded helper group: PASS (`67 passed` in its local grouping).
- E2 independent broader bounded helper grouping: PASS (`64 passed` in its local grouping).
- `py_compile`: passed for changed Python/test files.
- `git diff --check`: passed.
- Mac artifact smoke without local runtime artifacts failed closed as expected:
  - status `FALSE_NEGATIVE_CANDIDATE_PACKET_NOT_READY`
  - `scorecard_ready=false`
  - `bounded_demo_probe_authorized=false`
  - `operator_authorization_object_emitted=false`
  - `global_cost_gate_lowering_recommended=false`
  - `probe_authority_granted=false`
  - `order_authority_granted=false`
  - `promotion_evidence=false`

Linux source sync and canonical runtime smoke are pending the commit/push step.

## Constraints Checked

- No global Cost Gate lowering.
- No live/mainnet promotion.
- No bounded probe/order authority object.
- No Bybit private/signed/trading call.
- No PG write/schema migration.
- No crontab edit.
- No service restart/deploy/rebuild.
- No runtime env mutation.
- No Rust writer enablement.
- No plan inclusion.
- No active probe/order authority.
- No promotion proof.

## Aggressive Profit Hypotheses

1. Friction-adjusted false-negative candidate rotation
   - why it might make money: AVAX has strong edge but exact-confirm is blocked; another false-negative candidate may have comparable edge with lower touchability or authorization friction.
   - fastest safe test: source-only scorecard over existing false-negative packet plus bounded-chain friction artifacts.
   - required data: candidate packet, touchability preflight, placement plan, authorization packet, later candidate-matched order/fill/fee/slippage lineage.
   - failure condition: top alternatives are unmeasured or fail candidate identity alignment; no candidate has positive after-cost cushion after execution realism.
   - authority required: none for scorecard; exact bounded Demo authorization for any future order/probe.
   - max safe next action: review scorecard top candidates and collect missing candidate-scoped friction evidence.
   - score: expected_net_pnl_upside high; evidence_strength medium; execution_realism medium; cost_after_fees critical; time_to_test short; risk_to_account none; risk_to_governance low; autonomy_value high.
2. AVAX exact-confirm remains the shortest profit probe path
   - why it might make money: selected AVAX false-negative remains high-cushion and bounded chain is review-ready except typed-confirm.
   - fastest safe test: exact typed-confirm bounded Demo authorization, one post-only near-touch-or-skip order, then candidate-matched fill/fee/slippage review.
   - required data: authorization object, candidate-matched orders/fills, BBO, fees, slippage, matched blocked controls.
   - failure condition: no fill, negative net after fees/slippage, taker/crossing behavior, or control-matched edge decay.
   - authority required: exact bounded Demo typed-confirm only; no live.
   - max safe next action: do nothing runtime-facing until exact-confirm exists.
   - score: expected_net_pnl_upside high; evidence_strength medium; execution_realism medium; cost_after_fees critical; time_to_test short after auth; risk_to_account low Demo-only; risk_to_governance medium unless exact contract is preserved; autonomy_value high.
3. MM current-fee independent-window confirmation
   - why it might make money: a repeatable maker current-fee-positive cell avoids needing Cost Gate exception authority.
   - fastest safe test: read-only fill-sim/history replay for current-fee positive keys.
   - required data: fill-sim history, maker/taker split, queue realism, independent dates.
   - failure condition: single-window positivity, holdout decay, or maker realism fails.
   - authority required: none for replay.
   - max safe next action: source/read-only repeat-window analysis.
   - score: expected_net_pnl_upside medium; evidence_strength low-medium; execution_realism medium; cost_after_fees critical; time_to_test medium; risk_to_account none; risk_to_governance low; autonomy_value high.

## Status

`DONE_WITH_CONCERNS`: the source-only scorecard is implemented and locally verified after PA/E2/E4 review. Concern: it is not runtime-synced or canonical-smoked until after commit/push, and it must remain outside runtime admission, plan mutation, Cost Gate settings, and any proof/promotion path.
