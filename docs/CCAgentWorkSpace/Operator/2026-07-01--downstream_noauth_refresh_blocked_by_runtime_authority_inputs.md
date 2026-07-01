# Downstream No-Auth Refresh Runtime Blocker

- Status: `BLOCKED_BY_RUNTIME`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Active blocker: `P0-CURRENT-CANDIDATE-STANDING-AUTH-AND-EQUITY-INPUT-REFRESH-FOR-DOWNSTREAM-NOAUTH`
- Runtime manifest sha: `7c502ccf4b5d68573eaeddbb71ece1563b566fa66a4a9e704a6ea68491fc54bc`

PM attempted the E3-approved no-authority refresh needed before any new Phase A/B order-capable review. The run failed closed for two runtime input reasons:

- Fresh equity capture was approved only against localhost, but the runtime API is bound to `100.91.109.86:8000`; localhost was refused.
- The existing standing Demo authorization was rejected by the false-negative review/preflight helpers as invalid for preflight.

No public quote, active Decision Lease, private/order endpoint, order/cancel/modify, PG write, risk/service/env mutation, Cost Gate change, live/mainnet action, fill, PnL, or profit proof occurred.

Next safe checkpoint is to refresh/revalidate standing-auth consumption and the accepted Demo equity input path under E3 review. Do not rerun Phase A/B or broaden the API base without renewed review.
