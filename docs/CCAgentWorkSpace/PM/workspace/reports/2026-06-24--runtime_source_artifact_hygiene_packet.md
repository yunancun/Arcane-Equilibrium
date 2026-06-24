# Runtime Source / Artifact Hygiene Packet

Date: 2026-06-24
Active blocker: `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-DRIFT`
Implementation commit: `dd3017a09e655764f226acc96ff369102c28a94e`

## Session Loop State

- `session_goal`: Continue Profit-first Demo-learning Autonomy Improvement Loop under Aggressive Alpha Expansion Mode.
- `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-DRIFT`
- `blocker_goal`: Make runtime source/artifact drift reviewable without mutating runtime.
- `profit_relevance`: Stale runtime source and stale canonical artifacts can make profit-learning packets silently misrepresent the current research contract; hygiene must fail closed before any bounded probe review.
- `completed_blockers`: `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`, `P1-MM-CURRENT-FEE-REPEAT-WINDOW`
- `blocked_blockers`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains candidate/exact-confirm gated; no active probe/order authority object.
- `source_head`: Mac/source implementation target advanced from `25ce5fb4` to `dd3017a0`.
- `runtime_timestamp`: runtime read-only snapshot observed `2026-06-24T08:44:44Z`.
- `runtime_source_head`: `0886e24a`, stale vs source target.
- `pg_snapshot_timestamp`: not refreshed in this source-only blocker.
- `artifact_mtimes`: supplied `/tmp` snapshot showed current canonical MM/friction artifacts stale/incomplete relative to the source contract.
- `operator_action_required`: yes, but only for any later runtime source sync/artifact refresh; this packet itself grants no authority.
- `new_evidence_delta_required`: source/runtime/artifact drift evidence or a source-only way to classify it.
- `new_evidence_delta_found`: yes; runtime checkout and canonical artifact compatibility differ from current source contract.
- `acceptance_criteria`: no live/runtime mutation; supplied snapshots classify drift; empty evidence and authority/proof contamination fail closed; no order/probe/live authority.
- `next_blocker_id`: `P1-RUNTIME-SOURCE-SYNC-ARTIFACT-REFRESH-REVIEW`

## Anti-Repeat Decision

The current blocker was not a repeat of `P1-MM-CURRENT-FEE-REPEAT-WINDOW`. The MM repeat-window work was already source-complete, and runtime evidence showed a new delta: runtime source `0886e24a` and canonical artifacts did not satisfy the v466/v467 source contract. Re-running MM confirmation, bounded authorization, or generic audit would be a no-op. The safe source-only step was to extend the hygiene packet so this drift becomes explicit and fail-closed.

## Change

`helper_scripts/cron/runtime_health_hygiene.py` now accepts:

- `--source-status-json`
- `--artifact-status-json`

New packet sections:

- `source_checkout`
- `artifact_compatibility`

New answers:

- `runtime_source_drift_present`
- `artifact_compatibility_drift_present`
- `authority_boundary_violation_present`

The packet classifies `RUNTIME_SOURCE_HEAD_MISMATCH`, `CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT`, and combined `RUNTIME_HEALTH_HYGIENE_DRIFT`. It fails closed on empty supplied snapshots, unavailable snapshots, missing MM current-fee v466 repeat-window fields, missing/current-disabled false-negative candidate friction scorecard evidence, and nested/flattened authority/proof/writer/Cost Gate mutation signals including exact and prefixed `*_authority_granted_in_object` fields.

## Verification

- PA conditional guidance addressed.
- E2 final PASS.
- E4 final PASS.
- `PYTHONPATH=. python3 -m pytest -q helper_scripts/cron/tests/test_runtime_health_hygiene.py`: `22 passed`
- `PYTHONPATH=. python3 -m pytest -q helper_scripts/cron/tests`: `188 passed`
- `python3 -m py_compile helper_scripts/cron/runtime_health_hygiene.py helper_scripts/cron/tests/test_runtime_health_hygiene.py`: pass
- `git diff --check`: pass
- Supplied-snapshot CLI smoke: `RUNTIME_HEALTH_HYGIENE_DRIFT`, `RUNTIME_SOURCE_HEAD_MISMATCH`, `CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT`, runtime/artifact drift true, order/probe authority false.

## Boundaries

No Bybit call, no order/cancel/modify, no PG read/write/schema migration in this blocker, no crontab edit, no service restart, no env/auth/risk/order/strategy/runtime mutation, no Rust writer enablement, no live/mainnet action, no global Cost Gate lowering, no probe/order authority, no runtime artifact refresh, and no promotion proof.

## Aggressive Profit Hypotheses

1. Runtime source sync + artifact refresh may unlock current false-negative friction ranking.
   - Why it might make money: current source can evaluate false-negative candidates under the latest no-authority friction contract instead of stale latest artifacts.
   - Fastest safe test: operator-reviewed runtime source sync dry-run plus artifact-only refresh smoke.
   - Required data: clean runtime checkout, refreshed false-negative friction scorecard, current status row.
   - Failure condition: source stays stale, artifact missing, or authority/proof contamination appears.
   - Authority required: runtime source sync/artifact refresh review only; no order authority.
   - Max safe next action: build/review runtime source-sync + artifact-refresh packet.
   - Scores: expected_net_pnl_upside 7, evidence_strength 5, execution_realism 6, cost_after_fees 6, time_to_test 7, risk_to_account 1, risk_to_governance 3, autonomy_value 8.

2. Current-fee MM repeat-window path can be re-evaluated after source/artifact compatibility is clean.
   - Why it might make money: SOXLUSDT current-fee positive window remains a high-upside maker-fee path if repeat/OOS windows confirm.
   - Fastest safe test: artifact-only repeat-window refresh under the v466 contract.
   - Required data: fill_sim history window summaries with exact candidate keys and independent dates.
   - Failure condition: no second independent positive current-fee window or malformed exact-key evidence.
   - Authority required: none for research/artifact refresh; no order authority.
   - Max safe next action: refresh canonical MM confirmation after runtime source alignment.
   - Scores: expected_net_pnl_upside 6, evidence_strength 4, execution_realism 5, cost_after_fees 7, time_to_test 6, risk_to_account 1, risk_to_governance 2, autonomy_value 7.

3. False-negative candidate edge can be converted into a bounded Demo proposal only after hygiene is clean.
   - Why it might make money: the AVAX Sell false-negative path had strong net-after-cost blocked-outcome evidence, but needs candidate-matched execution proof.
   - Fastest safe test: refresh no-authority candidate/friction/touchability chain and produce a single operator review packet.
   - Required data: candidate-matched orders/fills, placement/touchability gates, no unattributed fills.
   - Failure condition: only non-candidate fills, stale PG `Working` rows, or exact-confirm absent.
   - Authority required: candidate-specific bounded probe authorization before any order.
   - Max safe next action: source/artifact hygiene clean packet, then candidate-specific authorization review.
   - Scores: expected_net_pnl_upside 8, evidence_strength 6, execution_realism 4, cost_after_fees 7, time_to_test 5, risk_to_account 2, risk_to_governance 4, autonomy_value 9.
