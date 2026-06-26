# Private Fee-Tier Read Envelope Design No-Read

1. `active_blocker_id`: `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-DESIGN-NO-READ`
2. `blocker_goal`: Build a source-only envelope for a future reviewed read-only private fee-tier capture, without performing the read or granting any runtime/order/probe authority.
3. `profit_relevance`: AVAX maker-first profitability depends on actual maker/taker fee economics. A private fee-tier read may later prove whether modeled costs are conservative or stale, but only if the evidence is candidate-scoped, sanitized, and reconstructable.
4. `constraints_checked`: no private fee read, no signed request, no credential load, no Bybit call, no PG query/write, no order/cancel/modify, no runtime/service/env/crontab mutation, no Rust writer/adapter enablement, no Cost Gate/freshness-gate lowering, no probe/order/live authority, no promotion/profit proof.
5. `previous_evidence_checked`: TODO v583, v583 fee-tier/maker-ratio report, session state `/tmp/openclaw/session_loop_state_20260626T130005Z_fee_tier_private_read_envelope_design_no_read.json`, latest runtime auth artifact, local fee-tier/maker-ratio evidence design smoke, Bybit fee-rate repo references, and todo-maintenance standard.
6. `new_evidence_delta_required`: P0 authorization must still lack an admitted auth delta; source-only envelope can progress if the v583 fee-tier/maker-ratio evidence design remains READY_NO_ORDER.
7. `new_evidence_delta_found`: Runtime auth refreshed to sha `71ecf0fff8c8fe76734f18ffbfd59022ee01ea9a5458d1b653e9e921decd205d`, mtime `2026-06-26T13:00:05.164306Z`, but remains `decision=defer`, no `authorization_id`, no probe/order authority, `typed_confirm_expected=None`. New local smoke artifact `/tmp/openclaw/20260626T130005Z_fee_tier_private_read_envelope_design_no_read/private_fee_tier_read_envelope_design.json` returned `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ`, sha `24180d6d04b11fdaa4163dc9f8dd0c916837ae0365ce9530afd54ab89eba7536`.
8. `anti_repeat_decision`: `P0_NO_OP_NO_ADMITTED_AUTH_DELTA__PROCEED_SOURCE_ONLY_PRIVATE_FEE_READ_ENVELOPE_DESIGN_NO_READ`; the auth artifact changed but still does not grant machine-checkable authority, so repeating P0 authorization would be no-op.
9. `action_taken_or_noop_reason`: Added `helper_scripts/research/cost_gate_learning_lane/private_fee_tier_read_envelope_design.py` and focused tests. The helper consumes the v583 READY_NO_ORDER evidence design and emits only a future-read envelope: endpoint/scope, credential minimization, redaction, response validation, proof attachment policy, and failure conditions.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| Actual account fee tier is better than modeled defaults | If actual maker fee is lower than assumed, AVAX maker-first micro-probe margin improves without changing strategy risk. | Review this envelope with E3/BB; no private read until a separate reviewed runtime invocation. | Fee-rate response for exact `AVAXUSDT`, response hash, timestamps, maker/taker bps, account scope, review id. | Endpoint unsupported, nonzero retCode, no exact symbol row, stale capture, or secret material persisted. | Future PM -> E3 -> BB approval for one read-only invocation. | Submit envelope for E3/BB review, still no read. | upside Medium; evidence Medium-low; realism Medium; cost impact High; time Medium; account risk None now; governance Low now; autonomy Medium |
| Modeled fee defaults are too optimistic | If actual fees are worse than assumed, this prevents a false profitable AVAX proof before any order authority is granted. | Same envelope, then future no-order read if reviewed. | Actual maker/taker rates and default/model comparison. | Conservative defaults are treated as proof or unsupported demo endpoint is treated as success. | Future read-only private endpoint review. | Preserve demo unsupported endpoint as no-proof. | upside Defensive; evidence Medium; realism High; cost impact High; time Medium; account risk None; governance Low; autonomy Medium |
| Fee provenance enables live-portable proof | A fee artifact with scope/time/hash/review id lets demo evidence later be compared to live/mainnet fee assumptions instead of relying on anecdotal costs. | Define proof-attachment fields now. | Candidate identity, fee schedule effective time, captured_at, review id, fill lineage. | Fee row cannot join candidate-matched fills or is cross-symbol/context-only. | None for design; future read review. | Keep proof attachment policy tied to outcome review. | upside Medium; evidence Medium; realism High; cost Low; account risk None; governance Low; autonomy High |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains the hard unlock if real auth appears; otherwise next safe blocker is `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-E3-BB-REVIEW-NO-READ`.
13. `why_not_repeating_current_blocker`: The envelope helper, tests, SCRIPT_INDEX entry, smoke artifact, and TODO closed marker exist. Repeating this design without changed fee-proof requirements or endpoint policy would be `NO-OP_ALREADY_DONE`.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Source Change

- Added `helper_scripts/research/cost_gate_learning_lane/private_fee_tier_read_envelope_design.py`.
- Added `helper_scripts/research/tests/test_cost_gate_private_fee_tier_read_envelope_design.py`.
- Updated `helper_scripts/SCRIPT_INDEX.md`.
- Updated `TODO.md`, changelog, worklog, and Operator note for v584 handoff hygiene.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_private_fee_tier_read_envelope_design.py` -> `9 passed`.
- Adjacent fee-tier evidence suite -> `28 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/private_fee_tier_read_envelope_design.py` -> passed.
- `git diff --check` -> passed.
- Real artifact smoke -> `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ`, sha `24180d6d04b11fdaa4163dc9f8dd0c916837ae0365ce9530afd54ab89eba7536`, all private-read/network/order/authority/proof answer flags false, full source path absent.

## Repo Chain

- PM triage and local implementation: completed because this is a narrow source-only helper derived from v583 acceptance.
- E2(explorer) adversarial review: first `DONE_WITH_CONCERNS`; found private-read/authority alias contamination and coverage gaps. PM fixed denylist, alias vocabulary scan, generic auth-field rejection, and independent tests. E2 final `DONE`: representative aliases return `AUTHORITY_BOUNDARY_VIOLATION`, not READY; focused tests `9 passed`.
- E4(worker) regression verification: `DONE_WITH_CONCERNS`; focused `5 passed`, adjacent `24 passed`, `py_compile`, and `git diff --check` passed before E2/E3 fixes. PM reran expanded post-fix suite locally: focused `9 passed`, adjacent `28 passed`, `py_compile`, `git diff --check`, and smoke passed.
- E3(explorer) security review: first `DONE_WITH_CONCERNS`; found broader alias contamination risk and full input path recording. PM fixed both. E3 final `DONE`: reported aliases fail closed, legitimate `future_private_read_authority_required` still READY, full path absent, no remaining E3 blocker for source-only closure. PM final smoke after BB-policy fixes is sha `24180d6d04b11fdaa4163dc9f8dd0c916837ae0365ce9530afd54ab89eba7536`.
- BB(explorer) exchange-facing design review: `DONE_WITH_CONCERNS`; endpoint shape matches Bybit V5 account fee-rate and Rust consumer. PM folded BB concerns into source: future capture accepts numeric fee rates including zero/negative maker rebate with labels and QC/BB review, and uses observed/captured time unless Bybit provides explicit effective timestamp.
- QA/PM final acceptance: final local verification passed; commit/push status is recorded in the PM response.

## PM Decision

This blocker closes only the source-only design. It does not permit a private read. A future read of `/v5/account/fee-rate` remains a separate runtime/exchange-facing action requiring PM -> E3 -> BB review and a bounded invocation plan.
