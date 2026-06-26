# Fee/Slippage/Maker-Taker Schema No-Order

1. `active_blocker_id`: `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER`
2. `blocker_goal`: Define a source-only, machine-checkable schema contract for future AVAX bounded Demo outcomes so real risk-adjusted net PnL after fees/slippage can be reconstructed before any proof/promotion review.
3. `profit_relevance`: The selected AVAX candidate can only become profitable evidence if future candidate-matched fills and same-side-cell controls include actual fees, slippage, maker/taker role, lineage, and reconstructable net PnL. This closes a proof-quality gap without changing orders or risk.
4. `constraints_checked`: No global Cost Gate lowering; no live promotion; no probe/order/live authority; no Bybit order/cancel/modify; no PG query/write; no crontab/service/runtime/env mutation; no Rust writer/adapter enablement; no `_latest` overwrite; no profit/proof claim.
5. `previous_evidence_checked`: v565 TODO; current-cap worksheet smoke `/tmp/openclaw/current_cap_staircase_risk_worksheet_smoke_20260626T082031Z/current_cap_staircase_risk_worksheet.json`; remote auth latest mtime `2026-06-26T08:30:47Z`, sha `c75fb61d...`; autonomous proposal latest sha `abe948aa...`; false-negative friction scorecard latest sha `ed57e0e5...`; Linux runtime source `dd22810e`, API active PID `2218842`.
6. `new_evidence_delta_required`: A distinct source-only fee/slippage/maker-taker schema gap remained after current-cap worksheet closure; no real P0 authorization delta was present.
7. `new_evidence_delta_found`: New helper `helper_scripts/research/cost_gate_learning_lane/fee_slippage_maker_taker_schema_contract.py`, tests, script index, and smoke artifact `/tmp/openclaw/fee_slippage_maker_taker_schema_smoke_20260626T083106Z/fee_slippage_maker_taker_schema.json` with sha `a08b23bf...`.
8. `anti_repeat_decision`: Proceeded with a new source-only blocker; did not rerun P0 authorization, candidate selection, control identity, or current-cap worksheet because same artifacts would add no evidence. Remote auth refresh is still defer/no-authority, not a grant.
9. `action_taken_or_noop_reason`: Implemented and tested `cost_gate_fee_slippage_maker_taker_schema_contract_v1`. READY requires future proof/control rows to include actual fee fields, actual slippage/reference price fields, maker/taker/post-only fields, order/fill lineage, and gross/cost/realized net bps reconstruction. Missing actual fee/slippage/liquidity role/lineage, modeled-cost-only rows, unattributed/cleanup fills, cross-symbol controls, and unreconstructable net PnL are proof-excluded.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| Fresh BBO read-only readiness path | AVAX modeled edge is high, but order admission needs fresh bid/ask and instrument filters to avoid stale placement and slippage surprises. | Source-only/read-only public BBO readiness design or reviewed public quote capture. | Fresh BBO, spread, instrument filters, tick/qty/min notional, artifact provenance. | BBO stale, wide spread, filter mismatch, authority contamination, or private/order endpoint use. | None for source-only design; E3/BB review for runtime/public quote capture; separate P0 auth before any order. | Design fresh BBO read-only readiness path, no order. | upside Medium-High; evidence Medium; realism Medium after quote; cost critical; time Fast; account risk None; governance Low-Medium; autonomy High |
| Maker-first micro tier policy | If AVAX edge survives fees, post-only near-touch maker fills may reduce cost and improve net PnL versus taker execution. | Source-only tier/placement policy using current cap ladder plus fee schema; no placement call. | Current cap tiers, fee tier assumptions, BBO spread, maker/taker fee labels, post-only rejection policy. | Taker fills dominate, post-only repeatedly misses, spread wipes edge, or fee labels missing. | None for policy design; E3/BB + P0 auth before probe/order. | Draft no-order maker placement policy. | upside Medium; evidence Low-Medium; realism Low until fills; cost favorable only if maker; time Medium; account risk None; governance Medium; autonomy Medium |
| Execution realism failure review | A candidate can look profitable in blocked-signal markouts but fail once real slippage/taker conversion is included; explicit review avoids false promotion. | Extend source-only review contract to flag taker rows, slippage outliers, fee gaps, and lineage gaps. | Future candidate fills/controls with actual fee/slippage/maker-taker labels. | Any missing actual cost field, unmatched control, unattributed fill, or unreconstructable net PnL. | None for design; bounded probe outcomes required later. | Keep outcome review gated on schema-compliant rows only. | upside Medium; evidence Medium design-only; realism High once fills exist; cost after fees critical; time Fast; account risk None; governance Low; autonomy High |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` if a real candidate-scoped authorization delta appears; otherwise after the operator-requested pause, `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER`.
13. `why_not_repeating_current_blocker`: The schema helper is source-backed, focused-tested, and smoke-tested; repeating it on the same current-cap worksheet would add no new evidence. P0 auth remains blocked/no-repeat because latest auth is still defer/no-authority.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_fee_slippage_maker_taker_schema_contract.py` -> `5 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/fee_slippage_maker_taker_schema_contract.py helper_scripts/research/tests/test_cost_gate_fee_slippage_maker_taker_schema_contract.py` -> pass
- Smoke JSON status: `FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY`
- Smoke no-authority answers: `bounded_demo_probe_authorized=false`, `probe_authority_granted=false`, `order_authority_granted=false`, `live_authority_granted=false`, `pg_query_performed=false`, `pg_write_performed=false`, `bybit_call_performed=false`, `order_submission_performed=false`, `promotion_evidence=false`, `promotion_proof=false`

## Pause

Operator asked: run this round, then pause and整理 TODO. PM will stop after v566 TODO is normalized and pushed.
