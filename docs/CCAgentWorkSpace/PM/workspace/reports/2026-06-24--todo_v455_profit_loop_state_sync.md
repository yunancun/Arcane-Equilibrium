# TODO v455 Profit Loop State Sync

## Session Loop State

- `session_goal`: Continue the Profit-first Demo-learning Autonomy Improvement Loop under Aggressive Alpha Expansion Mode.
- `active_blocker_id`: `P1-TODO-STATE-SYNC`
- `blocker_goal`: Reconcile the active TODO/operator-action source of truth with the already-pushed source-only Profit-first governance packets.
- `profit_relevance`: Prevents the loop from repeatedly dispatching stale P1 audits and keeps operator attention on the P0 cleanup gate needed before any bounded Demo candidate review.
- `source_head`: `ad09a5bd`
- `runtime_timestamp`: none queried in this turn; latest referenced read-only runtime source verification remains `c88deea7` from the v453 PM audit.
- `pg_snapshot_timestamp`: none queried in this turn.
- `operator_action_required`: none for this source-only sync; operator action remains required for Bybit order cleanup/quarantine, PG reconciliation/write, crontab/restart/deploy/source sync, and bounded probe/order/live authority.
- `new_evidence_delta_required`: Source-only TODO/changelog drift from the latest pushed governance packets.
- `new_evidence_delta_found`: TODO masthead and §6 still described P1 proof-exclusion, learning SSOT, cron expected-head hygiene, and anti-repeat governance as open after their source-only packets had landed.
- `acceptance_criteria`: Active state documents name `ad09a5bd`, distinguish P1 source-only closures from unresolved P0 operator gates, preserve no-authority/no-proof boundaries, and keep the next executable blocker pointed at operator-gated evidence-quality cleanup.
- `next_blocker_id`: `P0-PROFIT-EVIDENCE-QUALITY`

## Anti-Repeat Decision

- `status`: `DONE`
- `decision`: `source_only_progress_allowed_for_active_blocker`
- `reason`: This was not a repeat of a completed runtime audit; it corrected active-state drift caused by new source-only packets after the v453 audit.
- `bybit_call_performed`: false
- `pg_query_performed`: false
- `runtime_mutation_performed`: false
- `proof_claimed`: false

## Changes

- Updated `TODO.md` masthead to v455 and source checkpoint `ad09a5bd`.
- Updated TODO §6 to mark P1 source-only closures as complete while leaving P0 working-order/fill-lineage cleanup operator-gated.
- Updated `docs/CLAUDE_CHANGELOG.md` with v454-v455 entries.

## Aggressive Profit Hypotheses

1. `false_negative_candidate_subset`
   - `why_it_might_make_money`: The Cost Gate false-negative packet already ranks side-cells with positive after-cost blocked-signal evidence; a stricter clean-fill/lineage subset could isolate repeatable net edge without lowering Cost Gate.
   - `fastest_safe_test`: Source-only candidate review packet over existing artifacts, excluding unattributed fills and `flash_dip_buy` demo fill proof.
   - `required_data`: Ranked false-negative packet, clean attributed demo fills, matched blocked-signal controls, fee/slippage assumptions.
   - `failure_condition`: Candidate loses after excluding unattributed or non-candidate-matched fills.
   - `authority_required`: none for source-only review; operator approval required before any bounded Demo probe.
   - `max_safe_next_action`: prepare exactly-one operator review candidate after P0 evidence-quality cleanup.
   - `scores`: expected_net_pnl_upside=4, evidence_strength=3, execution_realism=2, cost_after_fees=3, time_to_test=4, risk_to_account=1, risk_to_governance=1, autonomy_value=5

2. `maker_microstructure_repeat_window`
   - `why_it_might_make_money`: Current-fee MM candidates have shown isolated positive net windows; repeat-window and OOS confirmation may identify a maker-ratio path that clears fees without capital-scale fee-tier assumptions.
   - `fastest_safe_test`: Artifact-only independent-window replay for the same candidate key and motif, with maker execution realism gates.
   - `required_data`: MM current-fee packet, fill_sim history, independent L1/orderbook windows, maker/taker realized cost model.
   - `failure_condition`: No repeated same-key or same-motif current-fee-positive window, or maker execution realism fails.
   - `authority_required`: none for replay; operator approval required before any probe/order.
   - `max_safe_next_action`: source-only replay/backfill request or packet, no live mutation.
   - `scores`: expected_net_pnl_upside=3, evidence_strength=2, execution_realism=3, cost_after_fees=3, time_to_test=3, risk_to_account=1, risk_to_governance=1, autonomy_value=4

3. `working_order_overhang_quarantine_alpha`
   - `why_it_might_make_money`: Deep stale working orders can contaminate fill attribution, capital allocation, and touchability diagnostics; quarantining them may expose clean strategy-specific edge and prevent false positives.
   - `fastest_safe_test`: Read-only stale/deep/open-order classification plus operator decision packet; no cancel/modify without explicit authorization.
   - `required_data`: Current exchange open orders, order intent lineage, demo fills, BBO/touchability snapshots.
   - `failure_condition`: Overhang is unrelated to attribution drift or cannot be classified without exchange/runtime access.
   - `authority_required`: operator authorization for Bybit cleanup actions; none for source-only classifier improvements.
   - `max_safe_next_action`: request operator-approved read-only/runtime snapshot or cleanup authorization if needed.
   - `scores`: expected_net_pnl_upside=2, evidence_strength=4, execution_realism=4, cost_after_fees=2, time_to_test=2, risk_to_account=2, risk_to_governance=2, autonomy_value=4
