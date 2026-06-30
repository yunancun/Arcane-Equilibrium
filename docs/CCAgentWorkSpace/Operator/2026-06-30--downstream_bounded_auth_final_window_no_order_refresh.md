# 2026-06-30 Downstream Bounded Auth + Final-Window No-Order Refresh

Status: `DONE_WITH_CONCERNS`

Current ETH Buy downstream bounded authorization and final-window no-order admission evidence have been refreshed under the active standing Demo envelope:

- Standing auth sha `a26666e71462b2fb6d11b1eedbdb9006e6b549393719e1e6933c4f348da3e4d3`
- Cap `954.18759777 USDT`
- Max probe orders `2`
- Bounded auth sha `59fd54c49574ee063f7ec303b357f00a3d62490c3e1127aa3faf297d8e9b985e`
- Final admission sha `5d26cf035375846c91273ca9accf33d3ac4a47ccc1bbb92f37b6b732644489eb`
- Final-window manifest sha `7ba6047de6e52d4820aeb3ce78e6ab4f0ff5b08b755f6814e2d3374c38acd0d2`

One short Demo Decision Lease/BBO window was opened and closed with no order submission. Lease `lease:d5d7a3c92e99` was released; post-run governance sha `19d926b9dfbcab10d801214f327100b7bc2e93733e5df396b99aea49610bf4d6` reports `lease_live_count=0`.

This grants no persistent order authority, no runtime admission, no writer/adapter enablement, no live/mainnet authority, no Cost Gate change, and no profit proof.

Next blocker: `P0-CURRENT-CANDIDATE-ACTUAL-ADMISSION-EXECUTION-ENVELOPE-REVIEW`. Any order-capable bounded Demo invocation must run as a separate checkpoint with a fresh active lease, fresh BBO/order shape, Guardian/Rust authority, auditability, and reconstructability in the actual invocation window.
