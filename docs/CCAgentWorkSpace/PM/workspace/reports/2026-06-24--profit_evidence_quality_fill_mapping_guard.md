# Profit Evidence Quality Fill Mapping Guard

Date: 2026-06-24
PM: Codex
Source checkpoint: `66f063ccbf3edfd2559527c4151fdac2fc74e24b`
Status: `BLOCKED_BY_OPERATOR_ACTION` for the P0 exchange cleanup blocker; source-only fill-lineage guard completed.

## Session Loop State

- `session_goal`: Continue Profit-first Demo-learning Autonomy Improvement Loop under Aggressive Alpha Expansion Mode.
- `active_blocker_id`: `P0-PROFIT-EVIDENCE-QUALITY`
- `blocker_goal`: Close or explicitly quarantine exchange working-order overhang and fill-lineage drift; ensure unattributed or lineage-incomplete fills never become promotion / bounded-probe proof.
- `profit_relevance`: Profit selection is only meaningful if future fill-backed PnL is reconstructable, candidate-attributed, fee/slippage-aware, and proof-eligible. Misattributed fills can create false profit evidence.
- `completed_blockers`: P1 source-only governance packets from earlier 2026-06-24 checkpoints: proof-exclusion guard, learning SSOT decision, no-authority autonomous proposal contract, runtime health hygiene packet, and anti-repeat session-loop packet.
- `blocked_blockers`: P0 working-order overhang cleanup/quarantine and runtime/exchange-local fill-lineage reconciliation remain operator-gated.
- `previous_report_paths`: `2026-06-24--profit_evidence_quality_operator_checkpoint.md`, `2026-06-24--profit_evidence_quality_proof_exclusion_guard.md`, `2026-06-24--demo-learning-autonomy-pm-current-state-report.md`, `2026-06-24--profit_first_session_loop_state_packet.md`, `2026-06-24--todo_v455_profit_loop_state_sync.md`.
- `source_head`: started from `bc3ed13b1a81ad49076fe337d7ac20100a6e8b70`; source checkpoint after repair is `66f063ccbf3edfd2559527c4151fdac2fc74e24b`.
- `runtime_timestamp`: not refreshed this round; no runtime action was taken. Prior runtime facts remain those in the v453/v455 reports.
- `pg_snapshot_timestamp`: not refreshed this round; no PG query/write was run.
- `artifact_mtimes`: not refreshed this round beyond source/docs artifacts in this repo.
- `operator_action_required`: yes. Bybit cancel/modify/close, PG reconciliation/write, crontab/restart/deploy/source sync, and bounded probe/order/live authority still require explicit operator authorization.
- `new_evidence_delta_required`: operator cleanup/quarantine or explicit runtime/exchange authorization for the P0 exchange blocker; otherwise only source-only reconstructability repair may proceed.
- `new_evidence_delta_found`: no new runtime/PG/operator delta. A source-only fill-lineage repair surface was found and completed.
- `acceptance_criteria`: no Cost Gate lowering; no probe/order/live authority; no Bybit/PG/runtime mutation; future REST-success dispatch-response orderId mappings are guarded by active pending state; stale mappings fall back to unattributed audit; focused tests and repo-chain reviews pass.
- `next_blocker_id`: `P0-PROFIT-EVIDENCE-QUALITY` operator cleanup/quarantine remains the next hard gate before `P0-PROFIT-CANDIDATE-SELECTION`.

## Anti-Repeat Decision

- `anti_repeat_decision`: `active_blocker_repeatedly_blocked_by_operator_action`
- Decision: do not rerun the same read-only exchange/PG audit without an evidence delta.
- Allowed action: complete a source-only guard that improves future fill lineage and proof quality without touching runtime, exchange, PG, risk, authority, or Cost Gate state.

## Source-Only Change

The patch adds a local event-consumer mapping guard for the fill-before-OrderUpdate race:

- `PendingOrderEvent::ExchangeOrderIdMapped` represents a Bybit `orderId -> orderLinkId` mapping observed from an existing successful primary REST order-create response.
- Dispatch emits that mapping event only after existing REST dispatch success and only when both IDs are non-empty.
- Pending registration records the dispatch-response mapping only when the target pending order still exists.
- Stale map hits are removed and deliberately fall back to unattributed audit instead of arbitrary symbol/side matching.
- Mapping cleanup now covers full fill, terminal OrderUpdate failure, DispatchFailed, ExchangeZeroClose, DCP clear, paper reset, and periodic sweep.

Important caveat: this is a source-only fill-lineage guard, not deployed/runtime-proven lineage closure. The new dispatch-response mapping path is active-pending guarded; the pre-existing OrderUpdate mapping path remains the existing source of exchange WS mappings and was not redefined as active-only in this patch.

## Verification

- `cargo test -p openclaw_engine pending_registration_order_type_tests -- --nocapture`
  - Result: command exited 0.
  - Focused module: 26 passed, 0 failed.
  - Warnings: pre-existing unrelated Rust test warnings only.
- `git diff --check`
  - Result: clean.

Repo-chain review:

- PA follow-up: `PASS`; stale-map blocker closed, no remaining P0/P1 misattribution or audit suppression issue.
- E2 follow-up: `PASS`; P2 lifecycle cleanup concern closed, no remaining P0/P1/P2 correctness issue.
- E4: `PASS`; no governance/risk/auditability/reconstructability blocker; no Cost Gate/probe/order/live/PG/Bybit/runtime mutation beyond source bookkeeping.
- QA/PM: `PASS`; required wording caveat is to call this source-only fill-lineage guard, not deployed/runtime lineage closure or profit proof.

## Boundary Statement

No global Cost Gate lowering, no live promotion, no probe/order authority, no Rust writer enablement, no PG write/query, no Bybit private/signed/trading call, no order cancel/modify/close, no runtime/env/service/crontab mutation, and no promotion proof were performed or claimed.

`flash_dip_buy` fills and unattributed fills remain excluded from bounded-probe proof, Cost Gate proof, promotion evidence, and risk-adjusted net PnL proof.

## Aggressive Profit Hypotheses

1. Candidate-matched near-touch maker bounded Demo path for high-scoring false-negative side-cells.
   - `why_it_might_make_money`: false-negative candidates show after-cost blocked-signal cushion, but current passive placement is too deep to collect fills; near-touch maker placement may convert signal edge into candidate-matched execution evidence.
   - `fastest_safe_test`: source-only operator review packet design after P0 cleanup/quarantine, with no authority grant.
   - `required_data`: clean candidate-attributed orders/fills, fresh BBO, fill/fee/slippage lineage, matched blocked controls.
   - `failure_condition`: repaired placement still produces no candidate-matched fills, adverse selection exceeds gross edge, or controls show no incremental edge.
   - `authority_required`: operator authorization for any bounded Demo probe; none for research packet drafting.
   - `max_safe_next_action`: do not select a candidate yet; wait for operator cleanup/quarantine or explicit quarantine of P0 evidence-quality blocker.
   - Scores: expected_net_pnl_upside high, evidence_strength medium, execution_realism medium, cost_after_fees medium, time_to_test medium, risk_to_account low until authorized, risk_to_governance low if kept proposal-only, autonomy_value high.

2. Current-fee MM repeat-window confirmation for the SOXLUSDT-style maker cell.
   - `why_it_might_make_money`: a single current-fee-positive maker cell has shown positive net after current fee, but needs independent repeat/OOS and execution-realism confirmation.
   - `fastest_safe_test`: artifact-only replay/accumulation of independent windows for the same cell and motif, no live/demo authority.
   - `required_data`: fill_sim history windows, maker/taker role realism, queue position, spread/flow regime, independent date coverage.
   - `failure_condition`: no repeated positive windows, train/holdout drift, maker fill rate collapses, or adverse selection consumes the edge.
   - `authority_required`: none for source/artifact replay; operator authorization before any bounded Demo probe.
   - `max_safe_next_action`: source-only repeat-window evidence refresh/design, not an order.
   - Scores: expected_net_pnl_upside medium, evidence_strength low-medium, execution_realism medium-low, cost_after_fees medium, time_to_test short-medium, risk_to_account low, risk_to_governance low, autonomy_value medium-high.

3. Fee/friction reduction path for maker-ratio and fee-tier sensitivity.
   - `why_it_might_make_money`: several maker paths are near the current fee wall; a lower effective fee or higher maker ratio can move marginal cells above net threshold without lowering the global Cost Gate.
   - `fastest_safe_test`: source-only fee-sensitivity packet update using existing fillsim/history artifacts; no exchange account action.
   - `required_data`: maker/taker mix, break-even maker fee by cell, account fee tier/rebate route assumptions, volume/capital feasibility.
   - `failure_condition`: required fee tier is capital-infeasible, edge disappears under execution realism, or route depends on live account privileges not granted.
   - `authority_required`: operator-only for any Bybit account/BD/fee-tier action; none for local analysis.
   - `max_safe_next_action`: produce a no-authority feasibility packet only after higher-priority P0 evidence-quality blocker is not being repeated.
   - Scores: expected_net_pnl_upside medium, evidence_strength medium, execution_realism medium, cost_after_fees high leverage, time_to_test medium, risk_to_account low for analysis, risk_to_governance low if no account action, autonomy_value medium.

## State Transition

- `status`: `BLOCKED_BY_OPERATOR_ACTION`
- `action_taken_or_noop_reason`: repeated exchange/PG audit was skipped; source-only fill-lineage guard was implemented and verified.
- `why_not_repeating_current_blocker`: the remaining P0 cleanup/quarantine requires operator authorization or explicit quarantine. Re-running the same read-only audit would violate the anti-repeat state machine and would not produce a valid new evidence delta.
