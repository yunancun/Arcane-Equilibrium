# GUI Percent Cap Semantics Guard

The correction is now enforced in source and runtime:

- GUI `P1 Risk/Trade=10.0%` = Rust `per_trade_risk_pct=0.1`, not `10 USDT`.
- Current Demo equity `9552.43426257` gives per-trade cap `955.24342626 USDT`.
- GUI `Max Single Position=25%` gives max-single-position budget `2388.10856564 USDT`.
- Local `10 USDT` remains only historical bounded diagnostic evidence and is explicitly marked non-authoritative.

Committed and pushed: `e4fb5c7f4087d55ed1a8330174234bdb3f00aa3e`.

Runtime `trade-core` is synced to that commit; crontab expected-head pins are `e4fb5c7f=11`, old `efa92a88=0`, line count `70`. No service restart and no order-capable action occurred.

Runtime admission is still blocked by Guardian `CAUTIOUS` / reconciler drift. This checkpoint does not grant order authority or profit proof.
