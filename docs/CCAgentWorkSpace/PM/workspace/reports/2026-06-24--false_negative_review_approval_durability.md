# False-Negative Review Approval Durability

Date: 2026-06-24
PM status: `DONE_WITH_CONCERNS`
Source branch: `main`

## Session Loop State

- `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE`
- `blocker_goal`: preserve explicit false-negative preflight approval durability so recurring default-defer refresh cannot erase candidate review progress before bounded Demo authorization review.
- `profit_relevance`: high. `grid_trading|AVAXUSDT|Sell` is review-ready with strong false-negative after-cost evidence; losing the approval artifact blocks the bounded Demo learning path before candidate-matched execution evidence can be collected.
- `completed_blockers`: `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`, `P1-LEARNING-LOOP-CLOSURE`, `P1-AUTONOMOUS-PARAMETER-PROPOSAL`
- `blocked_blockers`: `P0-BOUNDED-PROBE-AUTHORIZATION`, `P0-PROFIT-OUTCOME-REVIEW`
- `previous_report_paths`: `2026-06-24--candidate_matched_touchability_gate.md`, `2026-06-24--runtime_health_hygiene_packet.md`
- `source_head`: `d694fcac94f6fecb5090a1f4af6479f52e497f98` before this source fix.
- `runtime_timestamp`: `2026-06-24T08:42:08+02:00`
- `pg_snapshot_timestamp`: `2026-06-24 08:42:51.627196+02` read-only timestamp.
- `artifact_mtimes`: false-negative review/preflight and bounded chain latest all `1782283089.*` after the v461 refresh.
- `operator_action_required`: false for this source-only fix.
- `new_evidence_delta_required`: prove default-defer refresh preserves a fresh, aligned, no-authority approval artifact.
- `new_evidence_delta_found`: yes. v461 observed default-defer refresh can overwrite explicit approval and demote preflight to `OPERATOR_REVIEW_REQUIRED`.
- `acceptance_criteria`: default-defer must preserve fresh aligned approval; stale, mismatched, not-ready, or authority-bearing current packets must fail closed; no authority object or order/probe authority may be emitted.
- `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION`

## Anti-Repeat Decision

Decision: `source_only_progress_allowed_for_active_blocker`

Reason: this is a new source-only scope, `false_negative_review_approval_durability_v1`, not another broad audit. It protects the exact artifact chain needed for bounded Demo authorization review.

## Action Taken

- Added `--existing-operator-review-json` to `false_negative_operator_review.py`.
- Default `--decision defer` now preserves an existing approval only when all are true:
  - current candidate packet is fresh, schema-valid, ready, and no-authority;
  - existing review is fresh;
  - existing review is `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`;
  - existing review matches current side-cell and false-negative rank;
  - existing review answers confirm no runtime/probe/order authority and no Cost Gate lowering.
- Cron now passes `--existing-operator-review-json "$FALSE_NEGATIVE_OPERATOR_REVIEW_LATEST"` into default-defer review refresh.
- Added regressions:
  - fresh existing approval is preserved under default defer;
  - stale existing approval is not preserved;
  - authority-bearing current candidate packet is not masked by an old approval;
  - mismatched existing approval is not preserved;
  - preserved approval can feed false-negative bounded preflight while keeping all authority flags false;
  - cron static checks confirm the existing-review input is wired.

## Verification

- E2/E4 first review found a blocking preserve-before-authority-gate gap. PM fixed it by requiring `authority_preserved and packet_ready` before preserve.
- Focused operator-review + false-negative preflight: `7 passed, 88 deselected`
- Changed cron static: `15 passed`
- Cron static bundle: `18 passed`
- Full Cost Gate policy: `90 passed`
- Profitability + alpha runtime tests: `98 passed`
- Bounded authorization/touchability/placement: `26 passed`
- `py_compile`, `bash -n`, and `git diff --check`: passed
- Artifact smoke:
  - normal default-defer + fresh existing approval -> `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`, `defer_refresh_preserved_existing_approval=true`, no authority flags.
  - authority-bearing current packet + existing approval -> `AUTHORITY_BOUNDARY_VIOLATION`, no preserve, no authority flags.

## Constraints Checked

- No global Cost Gate lowering.
- No live/mainnet promotion.
- No bounded probe/order authority object.
- No Bybit private/signed/trading call.
- No PG write/schema migration.
- No crontab edit.
- No service restart/deploy/rebuild.
- No Rust writer enablement.
- No promotion proof.

## Aggressive Profit Hypotheses

1. Approval-durable AVAX bounded Demo path
   - why it might make money: the selected false-negative cell has strong after-cost replay evidence, but the review chain must not regress before authorization.
   - fastest safe test: artifact-only cron refresh preserving explicit approval, then defer-only authorization packet review.
   - required data: false-negative candidate packet, existing approved review, bounded preflight/touchability/placement/readiness chain.
   - failure condition: approval is stale, mismatched, or current packet gains authority-bearing fields.
   - authority required: none for this source fix; later structured bounded Demo authorization for any order/probe.
   - max safe next action: sync source and run artifact-only runtime smoke.
   - score: expected_net_pnl_upside high; evidence_strength medium; execution_realism medium; cost_after_fees unknown until probe; time_to_test short; risk_to_account none; risk_to_governance low after this fix; autonomy_value high.
2. Approval-preserving review ledger as reusable live-portability control
   - why it might make money: prevents autonomous learning from losing high-edge reviewed candidates due to cron drift, without relaxing gates.
   - fastest safe test: source-only status/log assertion and runtime latest artifact smoke.
   - required data: status log fields and latest artifacts.
   - failure condition: status JSON reports pending while latest approved should be preserved.
   - authority required: none.
   - max safe next action: add status fields if future audit needs stronger observability.
   - score: upside medium; evidence_strength high; execution_realism high; cost_after_fees neutral; time_to_test short; account risk none; governance risk low; autonomy_value high.
3. Candidate-specific maker probe queue
   - why it might make money: after approval durability, the next review packet can authorize tiny post-only near-touch attempts to collect candidate-matched fee/slippage evidence.
   - fastest safe test: defer-only authorization packet remains review-ready; explicit structured authorization only after review.
   - required data: candidate-matched BBO/order/fill/fee/slippage and matched controls.
   - failure condition: no candidate-matched fills or negative net edge after fees/slippage.
   - authority required: bounded Demo authorization object, not live.
   - max safe next action: prepare authorization review packet; do not emit authority automatically.
   - score: upside high; evidence_strength medium; execution_realism medium; cost_after_fees critical; time_to_test medium; account risk low under Demo cap; governance risk medium until exact authorization; autonomy_value high.

## Status

`DONE_WITH_CONCERNS`: source-only approval durability is implemented and locally verified. Remaining concern is runtime sync/artifact smoke after commit; no runtime or exchange mutation is required.
