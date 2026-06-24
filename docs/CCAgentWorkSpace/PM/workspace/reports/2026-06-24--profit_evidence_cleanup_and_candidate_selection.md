# 2026-06-24 -- Profit Evidence Cleanup And Candidate Selection

STATUS: DONE_WITH_CONCERNS

Scope: Profit-first Demo-learning Autonomy Improvement Loop under Aggressive
Alpha Expansion Mode.

Boundary: operator authorized Demo API actions in this session. This report
records a Demo-only risk-reducing cleanup plus source/artifact-only candidate
selection. It does not grant bounded-probe authority, order authority, live
authority, Cost Gate lowering, promotion proof, PG reconciliation writes, cron
edits, service restart, Rust writer enablement, or live/mainnet action.

## session_loop_state

| field | value |
|---|---|
| session_goal | Continue profit-first Demo-learning autonomy while preserving survival, Guardian/risk gates, Decision Lease, Rust authority, authorization, auditability, and reconstructability. |
| active_blocker_id | `P0-PROFIT-EVIDENCE-QUALITY`, then `P0-PROFIT-CANDIDATE-SELECTION` |
| blocker_goal | Clean or quarantine exchange working-order overhang and lineage drift; then select exactly one bounded Demo candidate review packet without granting authority. |
| profit_relevance | Candidate PnL can only be trusted after exchange exposure is clean and fills are candidate-attributed, fee/slippage-aware, and reconstructable. |
| completed_blockers | `P0-PROFIT-EVIDENCE-QUALITY` exchange cleanup completed with PG stale-row quarantine concern; `P0-PROFIT-CANDIDATE-SELECTION` selected one no-authority review candidate. |
| blocked_blockers | `P0-BOUNDED-PROBE-AUTHORIZATION` requires explicit candidate-specific operator authorization. |
| previous_report_paths | `2026-06-24--profit_evidence_quality_operator_checkpoint.md`, `2026-06-24--profit_evidence_quality_fill_mapping_guard.md`, `2026-06-24--demo-learning-autonomy-pm-current-state-report.md`. |
| source_head | Mac/origin `ae39b608ab6147d35ade2518e3f7284a182daa7b`; runtime checkout clean at `c88deea7ead57a6e7f7b8d06cba8f7f235ad6a92` during cleanup. |
| runtime_timestamp | `2026-06-24T06:48:12+02:00` preflight; cleanup executed shortly after. |
| pg_snapshot_timestamp | `2026-06-24 06:56:28.194455+02` read-only PG snapshot. |
| artifact_mtimes | false-negative candidate/operator-review latest artifacts mtime `1782275408.*`; cleanup evidence from control API response and post-clean reads. |
| operator_action_required | yes for the next blocker: candidate-specific bounded-probe authorization; also yes for any PG reconciliation/write, deploy/restart, crontab edit, Rust writer enablement, or live/mainnet action. |
| new_evidence_delta_required | yes: new operator Demo API authorization or runtime cleanup evidence after the prior operator-blocked checkpoint. |
| new_evidence_delta_found | yes: operator Demo API authorization plus successful control-plane Demo cleanup and exchange clean verification. |
| acceptance_criteria | Demo only; use control-plane path; no direct live/mainnet; no Cost Gate lowering; no probe/order authority; verify exchange orders=0 and positions=0; quarantine stale/unattributed/cleanup fills from proof; select exactly one no-authority review candidate. |
| next_blocker_id | `P0-BOUNDED-PROBE-AUTHORIZATION` |

## Anti-Repeat Decision

- Previous P0 reports were blocked by missing operator authorization.
- The operator supplied a new authorization delta: Demo API operations are
  authorized, while live/mainnet and global hard-boundary relaxations remain
  disallowed.
- Therefore the round did not rerun a read-only audit. It progressed to a
  runtime Demo-only cleanup through the reviewed control-plane path.

## Demo Cleanup Action

Review chain:

- `PM -> E3 -> BB -> PM`
- E3 and BB both passed the existing control API path and rejected direct Bybit
  REST as the immediate cleanup path.

Executed path:

- `POST /api/v1/strategy/demo/session/stop`
- CSRF double-submit was required and honored with matching `X-CSRF-Token` and
  `oc_csrf` values.
- Bearer token was loaded through a 0600 curl config, not printed in argv or
  reports.
- Runtime API endpoint was the running uvicorn process at
  `http://100.91.109.86:8000`; `127.0.0.1:8000` was not bound.

Response summary:

- `status`: `closed`
- `closed_all`: `true`
- `partial_failure`: `false`
- `errors`: `null`
- `demo_pause`: `{"paused": true}`
- `cancel_orders`: `found=20`, `cancelled=35`
- `orphan_sweep`: `found=1`, `swept=1`
- `verify`: `clean=true`, `attempts=1`, `elapsed_sec=0.34`
- `session`: `{"session_state": "stopped"}`

Post-clean readbacks:

- `/api/v1/strategy/demo/orders`: `regular_count=0`, `conditional_count=0`,
  `list_len=0`.
- `/api/v1/strategy/demo/positions`: `open_count=0`, `open_symbols=[]`.
- `/api/v1/strategy/demo/session/status`: returned `paused`, not `stopped`.
  This is recorded as a UI/control status hygiene concern, likely caused by
  process-local stop state under multi-worker uvicorn. The exchange state is
  clean and the engine is paused; no resume was performed.

## PG Lineage Quarantine

Read-only PG snapshot after exchange cleanup:

- `trading.orders` still has `874` Demo rows with `status='Working'` in the
  7-day window.
- Latest stale local rows include the cleanup close order
  `risk_close:ipc_close_symbol` for `SOLUSDT`, plus prior `flash_dip_buy`
  working rows.
- Recent fills show the cleanup `SOLUSDT` sell close fill as
  `risk_close:ipc_close_symbol`, taker, `fee=0.152878`, `slippage_bps=-1.4393`,
  `realized_pnl=0`.
- The SOL/ETH entry fills remain `strategy_name='unattributed:bybit_auto'`.
- 7-day unattributed fill count remains `6`.

Quarantine rule:

- Exchange overhang is cleaned, but stale PG `Working` rows are not corrected by
  this report and cannot be used as proof.
- Cleanup close fills are risk-reduction evidence only. They are excluded from
  bounded-probe proof, Cost Gate proof, promotion proof, and risk-adjusted net
  PnL proof because their entry lineage is incomplete or unattributed.
- Existing proof-exclusion remains effective: unattributed fills are audit
  evidence only, never promotion or bounded-probe proof.

## Exactly-One Candidate Review Packet

Selected candidate:

- `side_cell_key`: `grid_trading|AVAXUSDT|Sell`
- `strategy_name`: `grid_trading`
- `symbol`: `AVAXUSDT`
- `side`: `Sell`
- `dominant_horizon_minutes`: `60`
- `candidate_class`: `false_negative_after_cost`
- `outcome_count`: `48`
- `positive_outcome_count`: `48`
- `net_positive_pct`: `100.0`
- `avg_cost_bps`: `4.0`
- `avg_gross_bps`: `77.5511`
- `avg_net_bps`: `73.5511`
- `net_cost_cushion_bps`: `73.5511`
- `wrongful_block_score`: `147.1021`

Evidence source:

- `/tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_packet_latest.json`
  status `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`.
- `/tmp/openclaw/cost_gate_learning_lane/false_negative_operator_review_latest.json`
  status `PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW`, decision `defer`,
  selected `grid_trading|AVAXUSDT|Sell`.

Authority state:

- `global_cost_gate_lowering_recommended=false`
- `main_cost_gate_adjustment=NONE`
- `bounded_demo_probe_authorized=false`
- `operator_review_approved_for_preflight=false`
- `probe_authority_granted=false`
- `order_authority_granted=false`
- `promotion_evidence=false`
- `review_grants_runtime_authority=false`

Candidate review conclusion:

- `P0-PROFIT-CANDIDATE-SELECTION` is complete as a no-authority review packet.
- It is not a probe authorization, not an order request, not a Cost Gate change,
  and not a profit claim.
- Fastest safe next action is a candidate-specific bounded-probe authorization
  packet for operator review, including order budget, expiry, side-cell match,
  no global Cost Gate lowering, and explicit proof exclusions.

## Aggressive Profit Hypotheses

1. `false_negative_grid_avaxusdt_sell_60m`
   - `why_it_might_make_money`: blocked signals show 48/48 net-positive 60m
     outcomes after 4.0bp cost, with about 73.55bp average net cushion.
   - `fastest_safe_test`: candidate-specific bounded Demo probe authorization
     packet; no order until approved.
   - `required_data`: candidate-matched order/fill lineage, fresh BBO, fees,
     slippage, matched blocked controls, result and execution-realism review.
   - `failure_condition`: no candidate-matched fills, maker fill not realistic,
     controls lose edge, or after-fee/slippage net turns negative.
   - `authority_required`: explicit bounded-probe operator authorization.
   - `max_safe_next_action`: draft authorization packet only.
   - scores: expected_net_pnl_upside 9, evidence_strength 7,
     execution_realism 4, cost_after_fees 8, time_to_test 6,
     risk_to_account 3, risk_to_governance 2, autonomy_value 9.
2. `demo_cancel_all_to_rust_ipc_hardening`
   - `why_it_might_make_money`: live-applicable cleanup/control semantics reduce
     stale overhang and make future probes safer to repeat without Python REST
     cancel debt.
   - `fastest_safe_test`: source-only patch making Demo stop use Rust IPC
     `cancel_all_orders` like live, with tests; no deploy in this packet.
   - `required_data`: current IPC route, order-manager scoped cancel, stop-flow
     tests, status/verify behavior under multi-worker API.
   - `failure_condition`: patch weakens stop ordering, loses verify/error
     surfacing, or requires unsafe runtime restart before review.
   - `authority_required`: none for source patch/tests; deploy/restart separate.
   - `max_safe_next_action`: source-only design/patch after P0 authorization
     decision.
   - scores: expected_net_pnl_upside 4, evidence_strength 8,
     execution_realism 8, cost_after_fees 3, time_to_test 5,
     risk_to_account 1, risk_to_governance 2, autonomy_value 8.
3. `stale_pg_working_quarantine_backfill_design`
   - `why_it_might_make_money`: clean lifecycle truth prevents false positives,
     bad capital allocation, and repeated no-touch diagnostics on canceled
     exchange orders.
   - `fastest_safe_test`: source-only reconciliation/backfill design and dry-run
     report; no PG write.
   - `required_data`: exchange clean snapshot, PG stale `Working` rows, fills,
     orderLinkId/exchange id mappings, audit insertion semantics.
   - `failure_condition`: backfill cannot be made reconstructable/idempotent or
     would hide real lineage uncertainty.
   - `authority_required`: PG write approval for actual backfill.
   - `max_safe_next_action`: dry-run reconciliation packet only.
   - scores: expected_net_pnl_upside 5, evidence_strength 8,
     execution_realism 6, cost_after_fees 4, time_to_test 5,
     risk_to_account 1, risk_to_governance 3, autonomy_value 8.

## State Transition

- `P0-PROFIT-EVIDENCE-QUALITY`: `DONE_WITH_CONCERNS`
- `P0-PROFIT-CANDIDATE-SELECTION`: `DONE_WITH_CONCERNS`
- `P0-BOUNDED-PROBE-AUTHORIZATION`: next, `BLOCKED_BY_OPERATOR_ACTION`

`why_not_repeating_current_blocker`: the exchange overhang now has a runtime
evidence delta and is clean. Repeating the prior read-only inventory would
violate the anti-repeat rule. The remaining work is a new blocker: explicit
candidate-specific bounded-probe authorization or source-only hardening/design.

PM SIGN-OFF: DONE_WITH_CONCERNS.
