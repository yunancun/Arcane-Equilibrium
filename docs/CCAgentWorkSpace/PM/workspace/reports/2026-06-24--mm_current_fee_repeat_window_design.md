# PM Report — MM Current-Fee Repeat-Window Design Hardening

Date: 2026-06-24

## Session Loop State

- `session_goal`: Profit-first Demo-learning Autonomy Improvement Loop；Aggressive Alpha Expansion Mode。
- `active_blocker_id`: `P1-MM-CURRENT-FEE-REPEAT-WINDOW`
- `blocker_goal`: Turn the current-fee-positive MM candidate repeat-window gap into a fail-closed, reviewable, evidence-only design.
- `profit_relevance`: The SOXLUSDT maker cell is current-fee net-positive in one window (`0.715bps`) but cannot be treated as profitable until same-candidate independent repeat, OOS/walk-forward, maker execution realism, and bounded Demo outcomes exist.
- `source_head`: `c665cb05` at session start；implementation commit `09d0536b`.
- `runtime_timestamp`: `2026-06-24T08:12:24Z` from read-only `trade-core date -u`.
- `pg_snapshot_timestamp`: not refreshed in this source-only checkpoint.
- `artifact_mtimes`: runtime `mm_current_fee_confirmation_latest.json` mtime `2026-06-24T08:00:04.168634+00:00`; history scorecard mtime `2026-06-23T17:37:35.396383+00:00`.
- `previous_report_paths`: `2026-06-24--false_negative_candidate_friction_scorecard_canonical_ingestion.md`; previous MM packet history from v450.
- `new_evidence_delta_required`: source-only repeat-window design gap or new independent window evidence.
- `new_evidence_delta_found`: yes, source-only hardening opportunity plus runtime artifact showing the same candidate still has exactly one independent observed date.
- `operator_action_required`: none for this source-only checkpoint; future runtime source sync, service/cron mutation, PG writes, or candidate probe/order authority remain separate operator-reviewed actions.
- `acceptance_criteria`: exact same-candidate repeat evidence from `window_summaries`; malformed/missing/inconsistent evidence fails closed; authority/proof/mutation inputs fail closed; no Cost Gate lowering or probe/order/live authority; worklist exposes evidence without treating it as proof.

## Anti-Repeat Decision

`P1-MM-CURRENT-FEE-REPEAT-WINDOW` had not been completed as a source-only repeat-window design hardening checkpoint. It had new evidence delta because the runtime packet still showed a single current-fee-positive window and no repeat/OOS proof, while PA/E2/E4 identified concrete fail-closed gaps that could be fixed in source without runtime mutation.

Decision: proceed source-only. Do not rerun read-only audits as the endpoint; implement and verify the repeat-window contract.

## Action Taken

Implementation commit `09d0536bdae54884368b332b772fc3b20a41baa0`:

- `mm_current_fee_confirmation.py`
  - Recomputes same-candidate repeat observations from `fill_sim_history_scorecard.window_summaries`.
  - Requires exact `candidate_key` plus source/scope/symbol/queue/policy/track identity, positive current-fee net, and sample count.
  - Fails closed on missing summaries, malformed exact-key cells, and disagreement with `repeated_positive_keys`.
  - Forces `repeat_window_confirmed=false` in summary and answers whenever malformed candidate window evidence is present.
  - Fails closed on authority/proof/mutation contamination, including non-`NONE` `main_cost_gate_adjustment`, runtime/order/probe/live authority, PG/Bybit/order/crontab/service/runtime mutation markers, and promotion proof signals.
- `discovery_loop.py`
  - Carries repeat-window observed windows/dates, design status, consistency, remaining windows, and max safe next action.
  - Preserves explicit zero values when flattening evidence.
- `learning_worklist.py`
  - Whitelists the new evidence-only MM repeat-window fields.
- Tests
  - Cover exact-key matching, source/date de-dupe, missing summaries, malformed exact-key cells, mixed valid+malformed proof false, authority contamination, non-`NONE` authority values, artifact-only source scan, and explicit zero flattening.

## Review Chain

- PA: conditional approve; requested extending the existing packet and fail-closing on missing/malformed history, exact key only, no authority/proof signals.
- E2 first review: FAIL on malformed exact-key window proof and non-boolean authority fields.
- E4 first review: FAIL on non-`NONE` Cost Gate/runtime mutation input and explicit-zero flattening.
- PM/E1 fix: added strict window cell validation, expanded authority scanner, preserved zero flattening.
- E2 second review: FAIL on mixed valid+malformed case leaving proof boolean true.
- PM/E1 fix: `repeat_confirmed` now requires `not malformed_window_summaries`; added regression.
- E2 final: PASS.
- E4 final: PASS.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_mm_current_fee_confirmation.py` → `13 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` → `11 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` → `83 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_profitability_path_scorecard.py` → `18 passed`
- `python3 -m py_compile ...` → passed
- `git diff --check` → passed
- Runtime copied-artifact local smoke:
  - status `MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW`
  - candidate `edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only`
  - observed independent windows `1`
  - malformed count `0`
  - `repeat_window_confirmed=false`
  - order/probe/promotion authority flags false

## Boundary

Source/test/docs only. No Linux runtime sync, no runtime artifact refresh, no Bybit call, no PG write/schema migration, no crontab/service/env/auth/risk/order/strategy/runtime mutation, no Rust writer enablement, no live/mainnet, no global Cost Gate lowering, no probe/order authority, and no promotion proof.

## Aggressive Profit Hypotheses

1. Same-candidate MM repeat window
   - why it might make money: the SOXLUSDT back-queue informed-skip fill-only cell is already positive after current maker fees in one window.
   - fastest safe test: accumulate or read-only replay independent windows for the exact candidate key.
   - required data: fresh non-empty L1 fill_sim, history `window_summaries`, current fee round-trip, exact candidate identity.
   - failure condition: exact key fails to repeat across independent dates or malformed summaries appear.
   - authority required: none for read-only evidence; future probe/order authority requires separate review.
   - max safe next action: wait for next valid fill_sim refresh or run isolated read-only replay.
   - scoring: upside medium, evidence medium-low, execution realism medium-low, cost after fees currently positive but thin, time-to-test short, account risk low, governance risk low, autonomy value high.

2. Maker placement / queue-position variant search
   - why it might make money: current-fee edge may concentrate in a sub-region of queue position, spread, and informed-skip placement.
   - fastest safe test: source-only scan of adjacent queue/placement cells using the same malformed-proof guard.
   - required data: L1 history, fill_sim per-cell rows, maker fee tier, adverse selection markouts.
   - failure condition: train/holdout min gross remains below fee or repeat-date evidence fails.
   - authority required: none for research; no order/probe authority.
   - max safe next action: rank adjacent exact-key candidates by repeat-window readiness.
   - scoring: upside medium, evidence low, execution realism medium, cost after fees uncertain, time-to-test short, account risk low, governance risk low, autonomy value medium.

3. False-negative Cost Gate candidate with lower friction ordering
   - why it might make money: false-negative side-cells already show strong blocked-outcome net after fees, but touchability/placement friction blocks bounded probe proof.
   - fastest safe test: no-authority operator review packet comparing candidate-matched touchability repair alternatives.
   - required data: candidate-matched orders/fills, placement gaps, false-negative scorecard, bounded authorization packet state.
   - failure condition: candidate fills remain absent or repair plan requires unauthorized runtime/order mutation.
   - authority required: exact bounded Demo typed-confirm before any probe/order authority.
   - max safe next action: source-only repair-design comparison; do not submit/cancel/modify orders.
   - scoring: upside high, evidence medium, execution realism low-medium, cost after fees strong in blocked outcomes, time-to-test medium, account risk low until authorized, governance risk medium, autonomy value high.

## Status

`DONE_WITH_CONCERNS`

The source-level repeat-window design blocker is done. Concern remains that runtime source is not synced to `09d0536b`, and the actual MM candidate still has only one independent valid current-fee-positive window. This is not profit proof and not bounded-probe authority.

## Next Blocker

`P1-MM-CURRENT-FEE-REPEAT-WINDOW-EVIDENCE-ACCUMULATION`

Do not repeat this source-only hardening unless source HEAD, runtime artifact, history window summaries, or operator-reviewed authority state changes. The next non-repeating move is new independent same-candidate evidence or an explicit decision to pivot to another source-only aggressive alpha blocker.
