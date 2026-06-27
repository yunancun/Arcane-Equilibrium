# Operator Note: Guardian NORMAL Current-Cap Sizing

Guardian is back to `NORMAL`, so the effective single-order cap is no longer the old `0.7` Guardian-adjusted value. With GUI `P1 Risk/Trade=10.0%`, Demo equity `9552.43426257`, and GUI max-single-position `25%`, the current effective cap is:

- GUI per-trade cap: `955.24342626 USDT`
- Max-single-position budget: `2388.10856564 USDT`
- Guardian-adjusted cap at multiplier `1.0`: `955.24342626 USDT`
- Effective cap: `955.24342626 USDT`

Runtime current-cap sizing is READY_NO_ORDER at `145.7 AVAX / 954.6264 USDT`, but this is not execution clearance. Remaining blockers are a fresh active current-candidate Demo Decision Lease and fresh actual-admission BBO.

No order, live/mainnet authority, Cost Gate lowering, PG write, service restart, or profit proof occurred.
