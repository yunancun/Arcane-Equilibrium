# Maker Cost-Cushion Worksheet No-Order

1. `active_blocker_id`: `P1-AGGRESSIVE-ALPHA-MAKER-COST-CUSHION-WORKSHEET-NO-ORDER`
2. `blocker_goal`: Turn the fresh AVAX Sell no-order construction preview and modeled candidate edge into an explicit maker/taker fee/slippage stress worksheet, without order/probe/live authority.
3. `profit_relevance`: The candidate was already cap-constructible, but profitability still depends on surviving spread, fee, and slippage. The worksheet closes that source-only economics gap before any future bounded-probe review.
4. `constraints_checked`: No Bybit call, no private/auth/order endpoint, no order/cancel/modify, no PG query/write, no `_latest` overwrite, no runtime/env/service/crontab mutation, no Rust writer/adapter enablement, no Cost Gate/freshness-gate lowering, no probe/order/live authority, and no profit/proof claim.
5. `previous_evidence_checked`: TODO v576; v574 reroute sha `bc300277...`; atomic summary sha `98c7d75...`; construction preview sha `f721bc3a...`; runtime auth latest sha `bdaca35f...`, still `decision=defer`; runtime source clean at `dd22810e`.
6. `new_evidence_delta_required`: A source-only after-cost cushion packet that uses existing preview spread/notional and explicit fee/slippage assumptions, while labeling assumptions as research stress inputs instead of current fee proof.
7. `new_evidence_delta_found`: New helper `maker_cost_cushion_worksheet.py` plus real-artifact smoke packet `/tmp/openclaw/maker_cost_cushion_worksheet_20260626T111710Z/maker_cost_cushion_worksheet.json`, sha `074d2e1dc1a17a86cc5d88fa9e71aaf97d35b9a098af6e5d318e8b30111f9ab1`, status `MAKER_COST_CUSHION_WORKSHEET_READY_NO_ORDER`.
8. `anti_repeat_decision`: `PROCEED_SOURCE_ONLY_NEW_EVIDENCE_DELTA`; P0 auth had a refreshed auth artifact but still no admitted authority, so this round advanced only the source-only economics blocker.
9. `action_taken_or_noop_reason`: Implemented and tested `cost_gate_maker_cost_cushion_worksheet_v1`. The real AVAX packet computes maker conservative stress margin `66.9239bps` and taker failure-analysis margin `59.9239bps` using modeled `avg_net_bps=73.5511`, preview spread `1.6272bps`, maker fee assumption `2.0bps/side`, taker fee assumption `5.5bps/side`, and slippage buffer `1.0bps`. The packet states these are assumptions and may double-count upstream costs.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| AVAX maker-first bounded micro-probe | The no-order preview is fresh/cap-feasible and the conservative maker stress margin remains strongly positive under explicit assumptions. | Future operator review packet only; actual order path still requires candidate-scoped bounded Demo auth plus E3/BB order-envelope review. | Scoped auth, fresh BBO, post-only order envelope, candidate-matched fills, actual fee/slippage, same-side-cell controls. | No scoped auth, stale BBO, post-only reject/taker conversion, or net PnL after fees/slippage <= 0. | Candidate-scoped bounded Demo auth + runtime/order review. | Keep as review-only; do not place orders. | upside High; evidence Medium; realism Medium; cost favorable if maker; time Medium; account risk bounded only after auth; governance High; autonomy High |
| Taker-conversion kill switch | Taker stress margin is still positive in the worksheet, but taker fills are not maker-path success; explicit taker accounting can prevent false proof if post-only fails. | Add taker/failure labels to future review packet; no order now. | Liquidity role, post-only reject logs, actual fees/slippage, fill lineage. | Missing liquidity role, taker conversion counted as maker proof, or unattributed/cleanup fill enters proof. | None for design; auth for any order/fill path. | Carry taker fail-closed rule into future packet. | upside Medium; evidence Medium; realism High; cost critical; time Fast; account risk None now; governance Low; autonomy Medium |
| Fee-tier/cost-route optimization | If maker ratio improves or fee tier is lower than stress assumptions, real net cushion may expand without touching signal logic. | Source-only fee-tier route worksheet from actual account fee evidence, not assumptions. | Current account maker/taker fee tier, filled maker ratio, fee schedule provenance, volume tier path. | Fee evidence stale/missing, cushion relies on unverified discount, or route requires Cost Gate lowering. | Read-only fee evidence only; no order authority. | Defer until fee evidence is available. | upside Medium; evidence Low-Medium; realism Medium; cost High impact; time Medium; account risk None for source; governance Low; autonomy Medium |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `PAUSED_BY_OPERATOR_REQUEST`; on resume, first check for real P0 scoped auth delta, otherwise do not repeat this worksheet.
13. `why_not_repeating_current_blocker`: The worksheet now exists, is tested, and has a real-artifact smoke output. Repeating without changed fee assumptions, preview spread, candidate edge, or auth evidence would only regenerate equivalent source-only evidence.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_maker_cost_cushion_worksheet.py` -> `13 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_maker_cost_cushion_worksheet.py helper_scripts/research/tests/test_cost_gate_maker_first_micro_tier_policy.py helper_scripts/research/tests/test_cost_gate_fee_slippage_maker_taker_schema_contract.py helper_scripts/research/tests/test_cost_gate_fresh_bbo_readonly_readiness_path.py helper_scripts/research/tests/test_atomic_quote_adapter_preview_runner.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py` -> `84 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/maker_cost_cushion_worksheet.py` -> pass
- `git diff --check` -> pass
- `python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T111710Z_maker_cost_cushion_worksheet_no_order.json` -> pass
- `python3 -m json.tool /tmp/openclaw/maker_cost_cushion_worksheet_20260626T111710Z/maker_cost_cushion_worksheet.json` -> pass
- E2 adversarial follow-up -> `PASS` after fail-closed fixes for authority/proof aliases, status-string authority values, candidate identity completeness/self-consistency, and invalid notional/cost readiness.

## PM Decision

This is useful, but it is still research/proposal evidence only. The next order-adjacent step is not automatic. A future bounded Demo probe still needs scoped auth, fresh BBO, Decision Lease/Rust admission, E3/BB order-envelope review, and candidate-matched outcomes with actual fees/slippage.
