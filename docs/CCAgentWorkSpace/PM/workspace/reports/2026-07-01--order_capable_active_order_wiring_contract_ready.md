# Order-Capable Active Order Wiring Contract Ready

- Status: `DONE_WITH_CONCERNS`
- Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-E3-BB-REVIEW`
- Next blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-E3-BB-PACKET-REVIEW`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Session state: `/tmp/openclaw/session_loop_state_20260701T0304Z_order_capable_source_contract_patch/session_loop_state.json`
- Session state sha: `0babc68558cbb4590b9228ac2a19001557f357a87dcd5f09f504cf23b42ca890`
- Final session state: `/tmp/openclaw/session_loop_state_20260701T0304Z_order_capable_source_contract_patch/session_loop_state_final.json`
- Final source contract artifact: `/tmp/openclaw/order_capable_source_contract_patch_20260701T0304Z/active_order_wiring_contract_eth_buy_final.json`
- Final source contract sha: `0359e94452fa4db695d28caf25223935589721d9f464f333bf53f48760ae8160`

## Summary

PM found that the current order-capable source contract still failed as `ACTIVE_ORDER_WIRING_SOURCE_PATCH_REQUIRED` because the dispatch-boundary scanner did not recognize the production writer-mediated active bounded-probe dispatch path. This blocked an E3/BB order-capable Demo invocation packet.

E1 updated the source-only scanner and focused tests so the contract now requires both:

- `step_4_5_dispatch.rs` handoff evidence: active request construction, writer handoff, and `self.order_dispatch_tx.clone()`.
- `demo_learning_lane_writer.rs` production call-site evidence: `result.active_order_draft` branch, nested `order_dispatch_tx` branch, and actual `dispatch_active_bounded_probe_order_draft(tx, draft)` call.

E2 found two false-positive variants and returned the patch twice. E1 tightened the scanner each time. E2 final review returned `DONE` with no blocking findings.

## Verification

| Check | Result |
|---|---|
| Focused pytest | `27 passed` |
| py_compile | passed |
| scoped `git diff --check` | passed |
| E2 final review | `DONE`, prior HIGH resolved |
| ETH Buy contract status | `ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW` |

The final contract answers keep `active_runtime_probe_authority=false`, `active_runtime_order_authority=false`, `probe_authority_granted=false`, `order_authority_granted=false`, `live_authority_granted=false`, `order_submission_performed=false`, `pg_write_performed=false`, `global_cost_gate_lowering_recommended=false`, `main_cost_gate_adjustment=NONE`, `promotion_evidence=false`, and `promotion_proof=false`.

## Boundary

No runtime action, Bybit call, private endpoint, order, cancel, modify, PG write, service restart, env/crontab/risk mutation, Cost Gate lowering, live/mainnet action, fill, PnL, or profit proof occurred.

This checkpoint only makes the source contract ready for an E3/BB exchange-facing order-capable Demo review packet. It grants no order authority and does not consume or create a Decision Lease.
