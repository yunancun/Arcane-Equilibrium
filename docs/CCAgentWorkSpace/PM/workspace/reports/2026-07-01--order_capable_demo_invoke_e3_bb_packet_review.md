# Order-Capable Demo Invoke E3/BB Packet Review

- Status: `DONE_WITH_CONCERNS`
- Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-E3-BB-REVIEW`
- Next blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Packet: `/tmp/openclaw/order_capable_demo_invoke_review_20260701T035801Z/order_capable_demo_invoke_e3_bb_review_request.json`
- Packet sha: `2dc17635b838a546c0101d995c26842f66f4dfdab57c1536a5cc7a80b4fdd40e`
- Review decision manifest: `/tmp/openclaw/order_capable_demo_invoke_review_20260701T035801Z/review_decision_manifest.json`
- Review decision manifest sha: `f2364e3f2be98929f3ffd3c52445c038e4978d0bcf428339f7e01edcb70204b2`
- Final session state: `/tmp/openclaw/session_loop_state_20260701T035801Z_order_capable_demo_invoke_packet/session_loop_state_final.json`
- Final session state sha: `8aa42a95b9472c22b155fbbf54ab014c545ea21be28b2aafaab9574cd3643a72`

## Summary

PM added `current_candidate_order_capable_demo_invoke_review_packet.py` plus focused tests to make the order-capable Demo invocation handoff machine-checkable. The helper consumes the source active-order wiring contract, runtime standing Demo authorization, runtime canonical bounded Demo soak plan, renewed no-order active BBO manifest, and strict current-candidate order/fill scan.

The packet is a review request only. It does not acquire or reuse a Decision Lease, does not call Bybit, does not submit/cancel/modify orders, does not query/write PG, does not mutate runtime/service/env/risk/Cost Gate state, and does not grant live/mainnet, promotion, profit, or proof authority.

E2 found two hardening issues before final review: missing/invalid freshness timestamps could fail open, and the recursive authority checker did not cover several packet-scope aliases. PM fixed both and added regressions. Focused verification passed with `34 passed`, py_compile, diff-check, and direct CLI smoke.

## E3/BB Review

| Role | Verdict | Bound SHA | Notes |
|---|---|---|---|
| E3 | `APPROVE_WITH_CONDITIONS` | `2dc17635b838a546c0101d995c26842f66f4dfdab57c1536a5cc7a80b4fdd40e` | No execution/order/private endpoint/Decision Lease/runtime/live/mainnet/Cost Gate authority from packet alone. Fresh head/hash/auth/no-authority/gate/Rust/Lease/Guardian/BBO/order-shape/audit/reconstructability recheck required before any run. |
| BB | `APPROVE_WITH_CONDITIONS` | `2dc17635b838a546c0101d995c26842f66f4dfdab57c1536a5cc7a80b4fdd40e` | Packet permits no private/order endpoint or `POST /v5/order/create`. Future public GET scope is exact Demo market-data only; any future order must be max one Demo post-only near-touch limit-or-skip order with candidate-matched lineage and proof exclusions. |

## Verification

| Check | Result |
|---|---|
| Focused pytest | `34 passed` |
| py_compile | passed |
| scoped `git diff --check` | passed |
| direct CLI smoke | `CURRENT_CANDIDATE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_PACKET_READY True False` |
| E2 source review | `DONE_WITH_CONCERNS`, findings fixed |
| E3 review | `APPROVE_WITH_CONDITIONS` |
| BB review | `APPROVE_WITH_CONDITIONS` |

## Boundary

No runtime action, Bybit call, private endpoint, order, cancel, modify, PG query/write, service restart, env/crontab/risk mutation, Cost Gate lowering, live/mainnet action, fill, PnL, or profit proof occurred.

This checkpoint stops at exact-packet E3/BB review. The next step is a separate fresh invocation-window gate that must recheck source/runtime heads, packet/input hashes, standing/bounded auth freshness, no-authority inputs, active Decision Lease, BBO/instrument/order shape, Guardian/Rust authority, auditability, and reconstructability before any runtime/order-capable action.
