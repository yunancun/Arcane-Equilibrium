# False-Negative Candidate Friction Scorecard Canonical Ingestion

Date: 2026-06-24
PM status: `DONE_WITH_CONCERNS`
Source branch / implementation head: `main` / `909f3c86d407dfde4cbe9c6c4d030668df3e7bcb`

## Session Loop State

- `active_blocker_id`: `P1-FRICTION-SCORECARD-CANONICAL-INGESTION`
- `blocker_goal`: make the existing false-negative candidate friction scorecard recurring canonical learning-lane evidence for status, artifact-spine, discovery-loop, and learning-worklist visibility.
- `profit_relevance`: high. It keeps high-upside false-negative candidate rotation visible while `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked by exact typed-confirm.
- `completed_blockers`: source-only v464 friction scorecard triage.
- `blocked_blockers`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked by exact typed-confirm; `P0-PROFIT-OUTCOME-REVIEW` remains blocked until an authorized bounded probe has candidate-matched outcomes.
- `previous_report_paths`: `2026-06-24--false_negative_candidate_friction_scorecard.md`, `2026-06-24--bounded_probe_authorization_exact_confirm_gate.md`.
- `source_head`: base `0886e24ac45160a1de007e264556bcb7895fe79c`; implementation `909f3c86d407dfde4cbe9c6c4d030668df3e7bcb`.
- `runtime_timestamp`: not refreshed in this checkpoint; no runtime sync or cron run was performed.
- `pg_snapshot_timestamp`: not refreshed in this checkpoint; no PG query or write was performed.
- `artifact_mtimes`: no runtime artifact refresh was performed; this is source/test/docs only.
- `operator_action_required`: false for this source-only canonical ingestion; exact candidate-specific typed-confirm remains required before any bounded Demo probe/order authority.
- `new_evidence_delta_required`: source-only scope must add durable canonical ingestion rather than re-running the same exact-confirm authorization blocker.
- `new_evidence_delta_found`: yes. The scorecard now has recurring cron outputs, status fields, artifact spine registration, discovery-loop carry-through, and worklist evidence.
- `acceptance_criteria`: no global Cost Gate lowering, no live, no probe/order authority, no Bybit call, no PG write, no crontab/service/runtime mutation, no Rust writer enablement, no stale latest authority/proof leak, and no promotion proof.
- `next_blocker_id`: `P1-MM-CURRENT-FEE-REPEAT-WINDOW` if no exact bounded-probe typed-confirm delta appears.

## Anti-Repeat Decision

Decision: `source_only_progress_after_operator_authorization_blocker`

Reason: `P0-BOUNDED-PROBE-AUTHORIZATION` had no new exact typed-confirm evidence. Re-running the same read-only authorization audit would violate anti-repeat, so PM advanced the next allowed source-only aggressive-alpha checkpoint.

## Action Taken

`helper_scripts/cron/cost_gate_learning_lane_cron.sh` now refreshes:

`cost_gate_learning_lane/false_negative_candidate_friction_scorecard_latest.{json,md}`

The stage runs after bounded operator authorization and before shadow/result/execution-realism review. It uses same-cycle artifacts:

- `FALSE_NEGATIVE_CANDIDATE_PACKET_OUT`
- `BOUNDED_PROBE_TOUCHABILITY_PREFLIGHT_OUT`
- `BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT`
- `BOUNDED_PROBE_OPERATOR_AUTHORIZATION_OUT`

The cron wrapper now exposes refresh, max-age, top-limit, rc, skip reason, latest/out paths, and status-summary fields for the scorecard.

`helper_scripts/research/cost_gate_learning_lane/status.py` now carries scorecard rc/refresh/status/top/no-authority fields into the learning-loop summary. Nonzero scorecard rc contributes to loop `ERROR`.

`helper_scripts/research/alpha_discovery_throughput/artifact_spine.py` registers the scorecard as a `diagnostic_view`, not alpha evidence.

`helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` and `learning_worklist.py` carry compact scorecard evidence for review/worklist routing only.

## Review Findings And Fixes

- PA design review: PASS, with same-cycle input and no-authority constraints.
- E2 found a HIGH fail-closed issue: when current status row skipped/disabled the scorecard, `status.py` could fall back to stale `false_negative_candidate_friction_scorecard_latest.json` and rehydrate authority/proof fields.
- PM fix: current `status_row` is authoritative even when field values are `None`; artifact fallback is only used when there is no current status row.
- Regression: disabled current row plus stale latest authority/proof flags now keeps scorecard fields `None`.
- Regression: `false_negative_candidate_friction_scorecard_rc=7` drives loop `ERROR` while stale latest authority/proof flags remain ignored.
- E2 re-review: PASS.
- E4 coverage review: PASS after same-cycle packet assertion and rc-failure coverage.

## Verification

- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh`: PASS.
- `python3 -m py_compile` on touched Python modules/tests: PASS.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`: `15 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py`: `83 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`: `90 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_false_negative_candidate_friction_scorecard.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`: `19 passed`.
- `git diff --check`: PASS.
- Forbidden-token scan found only pre-existing env/test guard strings and readonly PG env loading; no new order/cancel/service path was added.

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
- No active probe/order authority.
- No promotion proof.

## Aggressive Profit Hypotheses

1. Friction-adjusted false-negative rotation
   - why it might make money: high-cushion blocked candidates can be ranked by both edge and bounded-probe friction, improving the next review choice if AVAX typed-confirm remains blocked.
   - fastest safe test: recurring source-only scorecard refresh and worklist evidence review.
   - required data: false-negative packet, candidate-scoped touchability, placement, authorization, later candidate-matched fills.
   - failure condition: stale/mismatched artifacts, no measured active candidates, or all alternatives fail execution realism.
   - authority required: none for scoring; exact bounded Demo typed-confirm for any future probe/order.
   - max safe next action: review canonical scorecard evidence only.
2. Current AVAX candidate exact-confirm path
   - why it might make money: AVAX remains a high net-cushion false-negative candidate, with current blocker reduced to exact typed-confirm.
   - fastest safe test: candidate-specific typed-confirm, then one bounded post-only Demo probe and outcome review.
   - required data: typed authorization object, candidate-matched order/fill/fee/slippage/control evidence.
   - failure condition: no fill, negative net after fees/slippage, taker execution, or matched-control decay.
   - authority required: exact typed-confirm only; no live.
   - max safe next action: wait for exact confirm; do not infer authority from broad Demo API authorization.
3. MM current-fee repeat-window path
   - why it might make money: repeatable maker-positive windows could avoid Cost Gate exception dependency.
   - fastest safe test: read-only fill-sim history repeat/OOS check.
   - required data: independent fill-sim windows, maker ratio, queue realism, fee sensitivity.
   - failure condition: single-window positivity, holdout decay, or maker realism failure.
   - authority required: none for replay.
   - max safe next action: source/read-only repeat-window analysis.

## Status

`DONE_WITH_CONCERNS`: canonical ingestion is implemented, reviewed, tested, committed, and ready for push. Concern: runtime Linux was not synced and no runtime artifact refresh was performed in this checkpoint; scorecard remains diagnostic/worklist evidence only.
