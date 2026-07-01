# Order-Capable Fresh-Window Packet Review Done

- Date: 2026-07-01
- Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`
- Next blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`
- State transition: `DONE_WITH_CONCERNS`
- Candidate: `grid_trading|ETHUSDT|Buy`

PM resumed from TODO v702 and corrected the fresh-window review packet helper so it binds active/next blocker to `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE` and computes the future order cap as the tighter of the bounded soak plan cap and current standing auth cap.

Source fix commit `362edf6bb0516a17f22776cb5809671910fcaae2` was pushed. Focused verification passed:

| Check | Result |
|---|---|
| Focused pytest | `9 passed` for `helper_scripts/research/tests/test_current_candidate_order_capable_demo_invoke_review_packet.py` |
| py_compile | passed for `current_candidate_order_capable_demo_invoke_review_packet.py` |
| scoped `git diff --check` | passed for helper and focused test |

## Fixed Packet

| Artifact | Path | SHA |
|---|---|---|
| Fixed packet | `/tmp/openclaw/order_capable_fresh_window_review_20260701T053415Z_after_packet_fix/packet/order_capable_demo_invoke_e3_bb_review_request.json` | `79bcbbad989be3782fcbd97a990b26b257b21bdbb37fc57c34060b7c19f1a2fb` |
| Review decision manifest | `/tmp/openclaw/order_capable_fresh_window_review_20260701T053415Z_after_packet_fix/review/review_decision_manifest.json` | `1e79fa481eb5185f169506288bc0fc4c77bf667007c564bcccb089b464202bc5` |
| Final session state | `/tmp/openclaw/session_loop_state_20260701T053415Z_order_capable_fresh_window_review/session_loop_state_final.json` | `ad81de98e880a5b2fa8a6497588b8e308b1b07a799322e269d9f4c9d822f672a` |

The fixed packet has empty loss-control blockers and empty authority-boundary violations. Its effective future cap is `954.18759458 USDT`, from `min(bounded_demo_soak_plan.max_demo_notional_usdt_per_order=954.18759777, standing_demo_authorization.risk_cap_lineage.resolved_cap_usdt=954.18759458)`.

## E3/BB Review

| Role | Verdict | Scope |
|---|---|---|
| E3 | `APPROVE_WITH_CONDITIONS` | No-order fresh-window preparation / Phase A/B gate path only. No order authority, no private/order endpoint, no persistent lease, no Cost Gate/live/mainnet/fill/PnL/proof authority. |
| BB | `APPROVE_WITH_CONDITIONS` | Future no-order Phase 0/A/B sequence only. Phase A limited to public Demo time/ticker/instruments-info GETs; Phase B requires fresh `TRADE_ENTRY` lease TTL `<=5s`; Phase C remains blocked. |

## Runtime Evidence

Runtime process recheck used the correct user namespace: `systemctl --user` reports `openclaw-trading-api.service` active/running, MainPID `1038429`, started `Tue 2026-06-30 00:46:29 CEST`, listening on `100.91.109.86:8000`. Runtime source remains `e16d3323cb58a549262f6bfa6f1ef48ca140aea0`, with runtime `origin/main` `c5fce0c6008b783e8264ce06a3a5f781fe18c26e`, status `ahead 8, behind 164`.

## Boundary

No public quote, active Decision Lease acquire/release, private/order endpoint, order/cancel/modify, PG query/write, service/env/risk mutation, Cost Gate lowering, live/mainnet authority, fill/PnL, or profit proof occurred.

The review is not direct runtime authority. The approved packet is bound to source head `362edf6bb0516a17f22776cb5809671910fcaae2`, while local source advanced after review through unrelated Stock/ETF static-guard commits. The next PM must refresh/recheck exact source/runtime heads, packet/input hashes, standing/bounded auth freshness, no-authority inputs, runtime user-unit/socket health, same-window Decision Lease, BBO/instrument/order shape, Guardian/Rust authority, auditability, and reconstructability. Any drift requires stop, refresh, or renewed review. Phase C/order submission still needs separate exact in-window E3/BB approval.
