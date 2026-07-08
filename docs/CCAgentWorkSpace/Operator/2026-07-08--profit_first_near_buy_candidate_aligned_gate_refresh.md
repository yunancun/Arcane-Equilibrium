# Operator Summary: Profit-First NEAR Buy Gate Refresh

Status: `READY_FOR_PM_E3_DISPATCH`

PM refreshed the current candidate-aligned no-authority chain for snapshot candidate `ma_crossover|NEARUSDT|Buy`. The current runtime candidate packet is newer than the earlier prompt snapshot: blocked outcomes are `764040`, avg net remains `64.983bps`, and `operator_review_ready=true`.

The old runtime standing authorization is still scoped to `grid_trading|ETHUSDT|Buy` and expired at `2026-07-08T01:53:48.341325+00:00`; PM did not use it as NEAR authority. A NEAR Buy standing authorization preview was generated for review only, with resolved cap `954.46746768` USDT from GUI-backed Rust RiskConfig plus accepted Demo equity. It was not materialized.

Operator revision accepted: candidate selection is dynamic, not fixed. E3 must re-read latest machine-readable runtime/no-authority artifacts before consuming the NEAR snapshot. If the latest selected candidate differs, this packet is `ROTATED`; the NEAR preview must not be materialized and PM must regenerate the chain for the latest selected candidate. Before BB, this dynamic selection still cannot use a new public/private Bybit call, Decision Lease, order, or probe.

No order, probe, cancel, public/private Bybit call, Decision Lease, runtime env/service mutation, DB write, Cost Gate lowering, live/mainnet action, or proof/promotion claim occurred.

Ready artifacts:

- PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.md`
- State packet: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.state_packet.json`
- Effect review: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.effect_review.json`
- E3 request: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.exact_scope_request.json`

Next action is to dispatch the revised exact PM->E3 request. E3 must recheck final source/runtime heads and latest candidate selection before consuming it. If a later step becomes exchange-facing, BB must be opened before any bounded Demo final window or exchange interaction.
