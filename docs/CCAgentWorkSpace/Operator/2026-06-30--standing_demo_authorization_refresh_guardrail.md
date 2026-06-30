# Standing Demo Authorization Refresh Guardrail

Date: 2026-06-30
Status: `DONE_WITH_CONCERNS`

PM refreshed the expired current ETH Buy standing Demo authorization without granting order, live, Cost Gate, or proof authority.

Key runtime result:

- Current standing auth: `/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`
- New sha: `a26666e71462b2fb6d11b1eedbdb9006e6b549393719e1e6933c4f348da3e4d3`
- Expiry: `2026-07-01T09:02:17.250395+00:00`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Mode: `0600`
- Max probe orders: `2`
- Refreshed cap: `954.18759777 USDT`
- Validator sha: `8dce62a676c3c5370579fd1e2687b0e9c0a64af7fa095e91fb6504cfc820c944`
- Readiness after refresh sha: `ee46a2ae8f84acdb1ebcd7c50ca50de59f76c1a2ae1535d12907dda073a2e1ac`

Source guardrail commit: `04ec9c55d73226149c2221df51d7ab1881abf796`.

Verification passed: source `py_compile`, focused tests `6 passed`, adjacent suite `52 passed`, post-refresh validator, post-refresh readiness. Runtime API/watchdog were active.

Boundary: no Decision Lease, no order/cancel/modify, no Bybit private/order call, no env/service/crontab mutation, no Cost Gate change, no live/mainnet authority, and no promotion/profit proof.

Next blocker: `P0-CURRENT-CANDIDATE-DOWNSTREAM-BOUNDED-AUTH-ADMISSION-REFRESH`.

Reason: the standing auth refresh changed the cap/order-shape lineage from prior cap `954.52067901 USDT` to refreshed cap `954.18759777 USDT`. Historical bounded auth, plan inclusion, and final-window artifacts must be rebuilt under the refreshed cap before any bounded Demo order-capable action.
