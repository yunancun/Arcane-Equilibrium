# No-Order Refresh Request Rotated By Source Drift Cbeab

Status: `ROTATED`

PM produced a fresh `cbeab710...` source-stability READY artifact and exact no-order E3/BB request, but final pre-E3 fetch moved source to `6449c3ad83119a3053c601eed5f3a7415daa5349`. The request is stale and non-consumable; E3/BB were not dispatched.

Key artifacts:

- Request sha `eb33f05cfb66fe683e258178241d0c516bccdee4cd22a80bb8438138a3d8c209`.
- READY sha `ef20f14f7d74ed733d02f34cb0f4f74ee4d8c5aa86fd4bfca1e6060590fd0a44`.
- Runtime snapshot sha `38370bf7e122652e5821e1f4f34769c268c1b34b4092df35da60f0dfbb2ef60e`.
- Final state sha `e6091f4b454722a1b5835e31c908291a987eab6323cf2b6727710b28730370d9`.

No Control API GET, Bybit call, Decision Lease, order/private endpoint, runtime mutation, Cost Gate change, live/mainnet, fill/PnL/proof, E3 dispatch, or BB dispatch occurred. Next PM should restart from `6449c3ad...` or newer.
