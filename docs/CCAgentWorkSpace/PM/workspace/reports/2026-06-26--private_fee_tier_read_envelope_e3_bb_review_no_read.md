# Private Fee-Tier Read Envelope E3/BB Review No-Read

1. `active_blocker_id`: `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-E3-BB-REVIEW-NO-READ`
2. `blocker_goal`: Review and harden the v584 private fee-tier read envelope for a future one-shot read-only invocation, without performing the private read or granting runtime/order/probe authority.
3. `profit_relevance`: Actual AVAX maker/taker fee economics can make or break risk-adjusted net PnL after fees/slippage. The review tightens the future fee capture path so a later Demo proof can be candidate-scoped, strict, and live-portable instead of relying on modeled costs.
4. `constraints_checked`: no private fee read, no signed request, no credential load, no Bybit account API call, no PG query/write, no order/cancel/modify, no runtime/service/env/crontab mutation, no Rust writer/adapter enablement, no Cost Gate/freshness-gate lowering, no probe/order/live authority, no promotion/profit proof.
5. `previous_evidence_checked`: TODO v584, v584 private fee-tier read envelope report and artifact, v583 fee-tier/maker-ratio design, latest runtime bounded auth artifact, repo Bybit reference, Rust `AccountManager` fee-rate parser/cache behavior, Rust demo unsupported fee-rate fallback, and official Bybit V5 fee-rate documentation.
6. `new_evidence_delta_required`: P0 authorization must still lack an admitted scoped auth delta; v584 READY_NO_READ envelope must exist; the review may only harden source/test/docs and local `/tmp` smoke artifacts.
7. `new_evidence_delta_found`: Runtime auth refreshed to sha `beb5a74d43907f98f9fa431a4b4bf1f8b4b25ebd661aa61ce9ff4380daf19039`, mtime `2026-06-26T13:30:53.436749Z`, but remains `decision=defer`, no `authorization_id`, no probe/order authority, `typed_confirm_expected=None`, `typed_confirm_readiness=PREFLIGHT_NOT_READY`. Hardened local smoke artifact `/tmp/openclaw/20260626T133535Z_fee_tier_private_read_envelope_e3_bb_review_no_read/private_fee_tier_read_envelope_design_hardened.json` returned `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ`, sha `c1081ff412fd1e855b8a6ff4856734789e6c9e862ed8124330c48f87e77c165b`.
8. `anti_repeat_decision`: `P0_NO_OP_NO_ADMITTED_AUTH_DELTA__P1_DESIGN_NO_OP_ALREADY_DONE__PROCEED_E3_BB_REVIEW_NO_READ`; P0 auth had a new sha/mtime but no machine-checkable authority, and v584 design is already closed, so the only safe progress was review/hardening.
9. `action_taken_or_noop_reason`: E3 reviewed the v584 envelope and found query-minimization, alias-contamination, and path-error hardening gaps. BB reviewed endpoint compatibility and found symbol-minimized reads must remain standalone proof artifacts, not runtime fee-cache replacements, and future proof parsing must be stricter than Rust's tolerant `parse_f64`. PM patched source/tests accordingly.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| Actual AVAX fee tier is materially better than modeled defaults | Lower maker fee or rebate can preserve positive maker-first margin under current cap without changing strategy risk. | Future one-shot fee-rate read only after separate runtime authorization; this round is design/review only. | Exact `AVAXUSDT` fee row, response hash, capture times, strict maker/taker parse, review id. | Symbol query unsupported, exact row missing, retCode nonzero, malformed fee fields, or sanitized artifact lacks provenance. | Future explicit PM/E3/BB runtime read authorization. | Stop at reviewed READY_NO_READ envelope. | upside Medium; evidence Medium; realism Medium; cost impact High; time Medium; account risk None now; governance Low now; autonomy Medium |
| Actual fees are worse than defaults | Finding worse actual fees early prevents a false profitable bounded probe and avoids optimizing around modeled-cost artifacts. | Same future one-shot read, but result can only inform proof exclusion/fail-closed policy. | Actual maker/taker rates and default/model comparison. | Unsupported endpoint or conservative defaults are counted as proof. | Future read-only private endpoint authorization. | Keep unsupported/default fees as no-proof. | upside Defensive; evidence Medium; realism High; cost impact High; time Medium; account risk None; governance Low; autonomy Medium |
| Strict fee provenance improves live portability | Candidate-scoped fee capture with strict parser/no cache replacement can later join fills without weakening live fee-cache assertions. | Attach hardened envelope fields to future outcome review packet. | Candidate identity, fee row, strict parse result, no-cache-replacement flag, fill lineage. | One-symbol read is used to satisfy broad runtime fee cache or live fee-count assertions. | None for source design; future runtime read authorization. | Preserve standalone-proof-only policy. | upside Medium; evidence Medium-high; realism High; cost Low; account risk None; governance Low; autonomy High |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains the hard unlock if real scoped auth appears; otherwise the actual private fee read is `BLOCKED_BY_RUNTIME_AUTHORIZATION` until a separate one-shot runtime read action is explicitly opened and reviewed.
13. `why_not_repeating_current_blocker`: E3/BB review, source hardening, tests, smoke artifact, TODO marker, and report now exist. Repeating this review without changed endpoint policy, auth evidence, or fee-proof requirements would be `NO-OP_ALREADY_DONE`.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Source Change

- Hardened `helper_scripts/research/cost_gate_learning_lane/private_fee_tier_read_envelope_design.py`.
- Updated `helper_scripts/research/tests/test_cost_gate_private_fee_tier_read_envelope_design.py`.
- Updated handoff docs: `TODO.md`, `helper_scripts/SCRIPT_INDEX.md`, changelog, worklog, and Operator note.

## Review Results

- E3(explorer): `DONE_WITH_CONCERNS`. PM fixed query minimization, cross-symbol persistence, camelCase/auth alias contamination, and basename-only non-object JSON errors.
- BB(explorer): `DONE_WITH_CONCERNS`. PM fixed standalone proof artifact/no runtime fee-cache replacement/no live fee-count satisfaction and strict missing/malformed maker/taker no-proof policy.
- E2(explorer): `DONE`; no findings after PM hardening.
- E4(worker): `DONE`; focused `10 passed`, adjacent `29 passed`, `py_compile`, `git diff --check`, and artifact assertions all passed. Confirmed no private/network/order/proof/authority flags.
- Official Bybit docs read-only check: `GET /v5/account/fee-rate`; `category` required; `symbol` optional and valid for `linear`; response includes `list[].symbol`, `takerFeeRate`, `makerFeeRate`.

## Verification

- Focused private fee-tier envelope tests -> `10 passed`.
- Adjacent fee-tier evidence suite -> `29 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/private_fee_tier_read_envelope_design.py` -> passed.
- `git diff --check` -> passed.
- Hardened artifact smoke -> `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ`, sha `c1081ff412fd1e855b8a6ff4856734789e6c9e862ed8124330c48f87e77c165b`; allowed query includes `symbol=AVAXUSDT`; strict parser required; malformed maker/taker fields fail closed; one-symbol proof cannot replace runtime fee cache; cross-symbol fee rows are not persisted; all action/proof/authority flags false.

## PM Decision

This blocker closes only review and hardening. It does not permit a private read. A future read of `/v5/account/fee-rate` remains a separate runtime/exchange-facing action requiring a fresh one-shot review id, runtime-host invocation plan, credential handling, redaction, strict exact-row parsing, and no PG/write/order/cache/proof mutation.
