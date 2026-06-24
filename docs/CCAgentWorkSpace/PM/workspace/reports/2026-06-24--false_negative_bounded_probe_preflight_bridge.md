# 2026-06-24 -- False-Negative Bounded Probe Preflight Bridge

STATUS: DONE_WITH_CONCERNS

Scope: Profit-first Demo-learning Autonomy Improvement Loop under Aggressive
Alpha Expansion Mode.

Boundary: source/test/docs plus read-only runtime artifact inspection. No
runtime deploy, no cron edit, no service restart, no PG write, no Bybit
private/trading call, no order/cancel/modify, no Rust writer enablement, no
global Cost Gate lowering, no probe/order/live authority, and no promotion
proof.

## session_loop_state

| field | value |
|---|---|
| session_goal | Continue profit-first Demo-learning autonomy while preserving survival, Guardian/risk gates, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| active_blocker_id | `P0-BOUNDED-PROBE-AUTHORIZATION` |
| blocker_goal | Decide whether the selected `grid_trading\|AVAXUSDT\|Sell` candidate can move toward bounded Demo probe authorization without broad Cost Gate relaxation or unbounded order authority. |
| profit_relevance | The selected false-negative has high after-cost upside, but it needs candidate-matched preflight, touchability, bounded operator authorization, and later fill-backed after-fee/slippage outcomes before it can become profit proof. |
| completed_blockers | `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`, `P1-LEARNING-LOOP-CLOSURE`, `P1-AUTONOMOUS-PARAMETER-PROPOSAL`, `P1-RUNTIME-HEALTH-HYGIENE`. |
| blocked_blockers | `P0-PROFIT-OUTCOME-REVIEW` remains blocked until an authorized bounded probe has candidate-matched outcomes. |
| previous_report_paths | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--profit_evidence_cleanup_and_candidate_selection.md`, plus the P1 source-only packets listed in TODO v457. |
| source_head | Started at `4e816f82`; source checkpoint after this patch is `3e560b44be59636132bda36dc787482172e73131`. |
| runtime_timestamp | `2026-06-24T07:07:27+02:00` read-only Linux snapshot. |
| pg_snapshot_timestamp | Not refreshed in this round; no PG query/write was performed. |
| artifact_mtimes | Runtime `/tmp/openclaw/cost_gate_learning_lane`: false-negative artifacts mtime `1782275408`; sealed/bounded authorization chain mtime `1782277204`. |
| operator_action_required | Yes for exact false-negative preflight approval, any future bounded probe authorization, any runtime cron/deploy/service mutation, and any PG reconciliation/write. |
| new_evidence_delta_required | Required for P0 authorization progress. |
| new_evidence_delta_found | Yes: runtime artifacts show selected false-negative `grid_trading\|AVAXUSDT\|Sell`, while current bounded authorization chain is still sealed-horizon `ma_crossover\|BTCUSDT\|Sell` and not ready. |
| acceptance_criteria | Build a no-authority false-negative candidate preflight bridge; preserve typed-confirm gates; do not authorize orders; prove with tests and actual AVAX artifact smoke. |
| next_blocker_id | `P0-BOUNDED-PROBE-AUTHORIZATION` remains active at the exact preflight-review approval gate; `P0-PROFIT-OUTCOME-REVIEW` is not reachable yet. |

## Anti-Repeat Decision

The anti-repeat packet returned `DONE_WITH_CONCERNS` with
`supplied_evidence_snapshot_delta_allows_active_blocker_progress`: source HEAD
changed since the prior report, runtime artifacts refreshed, and the new
artifact snapshot exposed a concrete mismatch between selected false-negative
candidate and the sealed-horizon authorization chain. This is not a repeat of
the prior cleanup/candidate-selection audit.

## Runtime Evidence Checked

- Linux repo read-only: clean `main` at
  `c88deea7ead57a6e7f7b8d06cba8f7f235ad6a92`.
- `false_negative_candidate_packet_latest.json`: status
  `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`.
- `false_negative_operator_review_latest.json`: decision `defer`, selected
  `grid_trading|AVAXUSDT|Sell`, all authority/proof flags false.
- `sealed_horizon_probe_preflight_latest.json`: status
  `OPERATOR_REVIEW_REQUIRED`, side-cell `ma_crossover|BTCUSDT|Sell`.
- `bounded_probe_operator_authorization_latest.json`: status
  `SEALED_HORIZON_PREFLIGHT_NOT_READY`, no authorization object.

An API readback attempted through `$OPENCLAW_API_TOKEN` failed because the token
was not exported in the non-interactive shell. No API mutation was attempted.

## Source Change

Commit `3e560b44be59636132bda36dc787482172e73131` added:

- `helper_scripts/research/cost_gate_learning_lane/false_negative_bounded_probe_preflight.py`
- `helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py`

It also updated:

- `bounded_probe_touchability_preflight.py` to accept
  `cost_gate_false_negative_bounded_demo_probe_preflight_v1`.
- `bounded_probe_operator_authorization.py` to accept the same preflight schema.
- Related focused tests and `helper_scripts/SCRIPT_INDEX.md`.

The new preflight converts a `REVIEWABLE_PARAMETER_PROPOSAL_READY` false-negative
proposal plus `cost_gate_false_negative_operator_review_v1` into a
candidate-matched `bounded_demo_probe_design_v1`.

## Artifact Smoke

Using copied, non-secret runtime JSON artifacts:

- `learning_ssot_decision`: `ARTIFACT_LEDGER_CURRENT_SSOT`; artifact ledger is
  current, PG-backed ledger is not cut over.
- `autonomous_parameter_proposal` for `grid_trading|AVAXUSDT|Sell`:
  `REVIEWABLE_PARAMETER_PROPOSAL_READY`, proposal id
  `cost_gate_parameter_proposal:461eddfe0d1dee6a`, no authority.
- `false_negative_bounded_probe_preflight` for `grid_trading|AVAXUSDT|Sell`:
  `OPERATOR_REVIEW_REQUIRED`; candidate alignment passed; only blocking gate is
  `false_negative_operator_review_approved_for_preflight`.

This means the AVAX candidate now has a concrete no-authority preflight bridge,
but broad Demo API authorization has not been converted into bounded probe
authority.

## Verification

- `python3 -m py_compile` for the new and modified helper modules.
- Focused bounded/false-negative pytest: `19 passed`.
- Broader Cost Gate bounded suite: `142 passed`.
- `git diff --check`: clean.

## Aggressive Profit Hypotheses

1. `avax_false_negative_bounded_probe_path`
   - `why_it_might_make_money`: `grid_trading|AVAXUSDT|Sell` has 48/48
     net-positive blocked outcomes at 60m with about `73.55bps` average net
     cushion after current cost assumptions.
   - `fastest_safe_test`: exact false-negative preflight approval, then
     candidate-matched touchability/placement/authorization review.
   - `required_data`: AVAX candidate preflight, fresh touchability audit,
     near-touch or skip placement review, exact bounded authorization object,
     fill/fee/slippage lineage, matched controls.
   - `failure_condition`: no candidate-matched touchable flow, adverse
     selection consumes edge, or after-fee/slippage realized net is non-positive.
   - `authority_required`: exact false-negative preflight approval, then
     separate bounded probe authorization; no live.
   - `max_safe_next_action`: source/artifact refresh of this preflight path
     only; no order.
   - scores: expected_net_pnl_upside `9`, evidence_strength `7`,
     execution_realism `4`, cost_after_fees `8`, time_to_test `6`,
     risk_to_account `3`, risk_to_governance `2`, autonomy_value `9`.

2. `candidate_matched_touchability_before_probe`
   - `why_it_might_make_money`: previous no-touch evidence was from mismatched
     flow; AVAX-specific touchability can distinguish execution blocker from
     alpha absence.
   - `fastest_safe_test`: run no-authority touchability/preflight artifacts for
     the AVAX preflight after exact preflight review approval.
   - `required_data`: order-to-fill audit, BBO coverage, side-cell match,
     placement gap, candidate-matched skip/submit previews.
   - `failure_condition`: AVAX sample cannot be matched or near-touch maker
     placement would cross/skip too often.
   - `authority_required`: none for artifact review; bounded authorization only
     before real probe orders.
   - `max_safe_next_action`: artifact-only touchability review once preflight
     approval exists.
   - scores: expected_net_pnl_upside `6`, evidence_strength `5`,
     execution_realism `7`, cost_after_fees `6`, time_to_test `5`,
     risk_to_account `1`, risk_to_governance `1`, autonomy_value `7`.

3. `false_negative_preflight_cron_wiring`
   - `why_it_might_make_money`: keeping false-negative candidates in the same
     bounded review chain prevents profitable blocked side-cells from being
     stranded behind sealed-horizon-only artifacts.
   - `fastest_safe_test`: source-only cron/status/worklist wiring for the new
     preflight, default defer/no-authority.
   - `required_data`: selected false-negative review artifact, autonomous
     parameter proposal artifact, preflight artifact, status/worklist ingestion.
   - `failure_condition`: wiring masks sealed-horizon blockers or creates a
     misleading ready status without typed-confirm approval.
   - `authority_required`: none for source/test/docs; runtime cron deploy
     separate.
   - `max_safe_next_action`: source-only wiring/tests, no runtime cron edit.
   - scores: expected_net_pnl_upside `5`, evidence_strength `6`,
     execution_realism `6`, cost_after_fees `4`, time_to_test `4`,
     risk_to_account `1`, risk_to_governance `2`, autonomy_value `8`.

## State Transition

- `P0-BOUNDED-PROBE-AUTHORIZATION`: `DONE_WITH_CONCERNS` for source bridge and
  AVAX no-authority preflight smoke.
- Actual bounded probe authorization: not granted; current state remains
  operator-review gated by exact false-negative preflight approval and later
  bounded authorization.

`why_not_repeating_current_blocker`: the prior next action was a generic
candidate-specific authorization review. This round found and closed a concrete
source gap: the selected false-negative candidate could not enter the bounded
preflight chain because the chain was sealed-horizon-only.

