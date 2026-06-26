# Fee-Tier Maker-Ratio Evidence Design No-Order

1. `active_blocker_id`: `P1-FEE-TIER-MAKER-RATIO-EVIDENCE-DESIGN-NO-ORDER`
2. `blocker_goal`: Build a source-only evidence contract for future AVAX bounded Demo proof to carry account fee-tier provenance, maker/taker labels, maker ratio, actual fees/slippage, and after-cost PnL reconstruction.
3. `profit_relevance`: The AVAX path may be profitable only if real after-fee/maker execution economics survive. This design reduces the chance that future Demo outcomes look profitable under modeled or missing costs, and keeps the evidence portable for later live review without granting live/order authority.
4. `constraints_checked`: no private fee read, no Bybit call, no PG query/write, no order/cancel/modify, no runtime/service/env/crontab mutation, no Rust writer/adapter enablement, no Cost Gate/freshness-gate lowering, no probe/order/live authority, no promotion/profit proof.
5. `previous_evidence_checked`: TODO v582, todo-maintenance standard, latest typed-confirm runtime sync report, runtime latest auth artifact, existing fee/slippage schema artifact, existing maker-first micro-tier policy artifact, SCRIPT_INDEX, and focused adjacent helper tests.
6. `new_evidence_delta_required`: P0 auth needed no admitted authorization delta before moving source-only; the source-only path needed existing no-authority auth/schema/policy inputs and a real artifact smoke showing READY_NO_ORDER without authority flags.
7. `new_evidence_delta_found`: Runtime auth naturally refreshed to sha `020b477d3581b3423cb4bf6dc4b7269eedc11b679d7b5030fb049df330a65602`, mtime `2026-06-26T12:45:04.172027Z`, but remained `decision=defer`, no `authorization_id`, no probe/order authority, and `typed_confirm_expected=None`. The new local smoke artifact `/tmp/openclaw/20260626T124030Z_fee_tier_maker_ratio_evidence_design_no_order/fee_tier_maker_ratio_evidence_design.json` returned `FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_READY_NO_ORDER`, sha `ce17dffeb80a840d023b458580a87d37e4ba963b9dbcc2f8916904e682750375`.
8. `anti_repeat_decision`: `P0_NO_OP_NO_ADMITTED_AUTH_DELTA__PROCEED_SOURCE_ONLY_P1_FEE_TIER_MAKER_RATIO_DESIGN`; the P0 auth artifact had a new sha/mtime but no machine-checkable authorization delta, so replaying P0 authorization would be repeat work. Source-only fee-tier/maker-ratio design was the next safe blocker.
9. `action_taken_or_noop_reason`: Added `helper_scripts/research/cost_gate_learning_lane/fee_tier_maker_ratio_evidence_design.py` and focused tests. The helper fails closed on authority-bearing inputs, stale exact typed confirms, candidate mismatch, non-ready fee schema, or non-ready maker policy; it emits only a no-order evidence contract and no runtime authority.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| Account fee-tier turns AVAX from modeled to real edge | Maker/taker fee tier can materially change net bps for micro-probes; actual fee evidence may preserve positive edge or expose a false positive before orders scale. | Source-only private fee-tier read envelope; no private read in this round. | Fee schedule source/hash, effective time, account scope, maker/taker bps, fee currency policy, E3/BB review id. | Fee tier is modeled, stale, unscoped, or cannot be tied to candidate-matched fills. | Future PM -> E3 -> BB review for private read only. | After resume, design read-only fee-tier envelope without performing the read. | upside Medium; evidence Medium-low; execution realism Medium; cost impact High; time Medium; account risk None now; governance Low now; autonomy Medium |
| Maker-ratio threshold separates good AVAX fills from taker leakage | The strategy may only make money when fills are actually maker/post-only; measuring maker notional ratio prevents taker conversions from masquerading as alpha. | Add maker-ratio contract now; later require candidate-matched Demo fills with liquidity-role labels. | Attempt/order/fill lineage, maker/taker filled notional, liquidity role, TIF, post_only, fees, slippage. | Missing maker/taker label, taker fills counted as maker proof, cleanup/unattributed fills enter proof. | Future bounded Demo auth and order-envelope review. | Keep maker-ratio requirement attached to any future outcome review. | upside Medium-high; evidence Medium; realism Medium; cost favorable if maker; time Medium; account risk bounded only after auth; governance Low; autonomy High |
| Proof-exclusion hardening prevents false profit promotion | Excluding unattributed, cleanup/risk-close, cross-symbol, modeled-fee, manual/replay-only, and single-window positives keeps learning from optimizing artifacts instead of net PnL. | Contract-level exclusions plus tests; no runtime action. | Candidate identity, controls, fill lineage, fee/slippage evidence, repeat/OOS plan. | Any excluded fill/result is counted toward Cost Gate, promotion, or bounded-probe proof. | None for source contract; future QC/PM for outcome review. | Done for this helper; enforce in future outcome packets. | upside Medium; evidence High for governance; realism High; cost Low; time Fast; account risk None; governance Low; autonomy High |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains the hard unlock if a real auth delta appears; after the requested pause and absent P0 delta, the next source-only blocker is `P1-FEE-TIER-PRIVATE-READ-ENVELOPE-DESIGN-NO-READ`.
13. `why_not_repeating_current_blocker`: The helper, tests, SCRIPT_INDEX entry, smoke artifact, and TODO closed marker now exist. Repeating it without changed fee schema, maker policy, selected candidate identity, or auth packet contract would be `NO-OP_ALREADY_DONE`.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Source Change

- Added `helper_scripts/research/cost_gate_learning_lane/fee_tier_maker_ratio_evidence_design.py`.
- Added `helper_scripts/research/tests/test_cost_gate_fee_tier_maker_ratio_evidence_design.py`.
- Updated `helper_scripts/SCRIPT_INDEX.md`.
- Normalized `TODO.md` v583 back to active dispatch queue format per `docs/agents/todo-maintenance.md`.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_fee_tier_maker_ratio_evidence_design.py` -> `8 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_fee_tier_maker_ratio_evidence_design.py helper_scripts/research/tests/test_cost_gate_fee_slippage_maker_taker_schema_contract.py helper_scripts/research/tests/test_cost_gate_maker_first_micro_tier_policy.py` -> `19 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/fee_tier_maker_ratio_evidence_design.py` -> passed.
- `git diff --check` -> passed.
- Real artifact smoke -> `FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_READY_NO_ORDER`, sha `ce17dffeb80a840d023b458580a87d37e4ba963b9dbcc2f8916904e682750375`, all authority/order/proof answer flags false.

## Repo Chain

- PM triage and implementation: completed locally because the change is a narrow source-only helper and TODO normalization.
- E2(explorer) adversarial review: first `DONE_WITH_CONCERNS`; found incomplete candidate identity and truthy typed-confirm marker gaps. PM fixed both with regression coverage. E2 follow-up `DONE`: incomplete identity returns `AUTH_PACKET_INPUT_NOT_READY`, truthy `typed_confirm_matches` returns `AUTH_PACKET_TYPED_CONFIRM_UNSAFE`, focused tests `8 passed`.
- E4(worker) regression verification: `DONE`; focused `5 passed`, adjacent `16 passed`, `py_compile`, and `git diff --check` passed before the E2 fix. PM reran the expanded post-fix suite locally: focused `8 passed`, adjacent `19 passed`, `py_compile`, `git diff --check`, and smoke passed.
- QA/PM final acceptance: accepted as source-only `DONE_WITH_CONCERNS`.

## PM Decision

This blocker is closed with concerns because the design is not fee proof, not maker-ratio proof, not order admission, and not profit evidence. It is only a contract for future bounded Demo outcomes to be reconstructable after real costs.
