# No-Order Refresh Request Rotated By Source Drift D89

Status: `ROTATED`

PM produced a fresh `d89c0278...` source-stability READY artifact and exact no-order E3/BB request, but final pre-E3 fetch moved source to `b71847faacf26529f0641c2bce325c2fd39bdafb`. The request is stale and non-consumable; E3/BB were not dispatched.

Key artifacts:

- Request sha `6964855a284f3e0d3b593dfdb2a0c268c1409ba7062b216f83b108f4d4e8ab8b`.
- READY sha `579dbf6b305effa17c884f95a130779ef91652c37f42522c7b916fc56fadfe2c`.
- Runtime snapshot sha `09f1a2be691e46e4f39af60f206c3379ced152f135c6332902437c35f8dd8197`.
- Final state sha `8c2d3296ec83375d53634e408503e4fc331b4cf9047c261b8ffb112200c2f0bb`.

No Control API GET, Bybit call, Decision Lease, order/private endpoint, runtime mutation, Cost Gate change, live/mainnet, fill/PnL/proof, E3 dispatch, or BB dispatch occurred. Next PM should restart from `b71847fa...` or newer.
