# Operator Note: Standing Auth Explicit AVAX Bounded Auth Object Review

State transition: `DONE_WITH_CONCERNS`.

The GUI risk correction is now deployed in source/runtime for this path. GUI `P1 Risk/Trade=10.0%` is treated as `per_trade_risk_pct=0.1`, resolving the per-order cap to `955.24342626 USDT` from accepted Demo equity. The old `10 USDT` value is not authority.

New timestamped artifact:

- `/tmp/openclaw/standing_auth_explicit_avax_review_after_sync_20260627T0348Z/bounded_probe_operator_authorization_authorize_after_sync.json`
- sha `8bbd865688de2fa7c067927383e584a4ca24dddca797a1ebbc45da15a7cd3cea`
- status `BOUNDED_DEMO_PROBE_AUTHORIZED`
- auth id `standing-demo-9309f8073f60d3db`
- candidate `grid_trading|AVAXUSDT|Sell`
- max probe orders `2`
- expires `2026-06-27T14:51:58.043996+00:00`
- confirmation source `standing_demo_authorization`

No `_latest` overwrite, plan mutation, writer enablement, order, live authority, Cost Gate change, active runtime authority, or profit proof occurred.

Next safe step: no-order bounded Demo admission envelope review using this timestamped auth object. Execution remains blocked until Decision Lease, Guardian risk gate, Rust authority admission, fresh actual-admission BBO, auditability, reconstructability, and no risk expansion all pass.
