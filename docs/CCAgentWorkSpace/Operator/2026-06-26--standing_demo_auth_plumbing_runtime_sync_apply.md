# Standing Demo Auth Plumbing Runtime Sync Apply

Status: `DONE_WITH_CONCERNS`

Runtime `trade-core` was fast-forwarded from `b224c759...` to `69f6c4b2...`, and 11 crontab expected-head pins were replaced to the same target. Line count stayed 70; `OPENCLAW_ALLOW_MAINNET=1`, bounded-probe adapter enablement, and probe outcome recording expansion remained absent.

Linux verification passed: auth focused `21 passed`, cron static `24 passed`, adjacent alpha/profitability `140 passed`, `git diff --check`, bash syntax, and py_compile. No service restart/rebuild, PG query/write, Bybit/API/order/cancel/modify, Cost Gate lowering, writer/adapter enablement, active probe/order/live authority, or profit proof happened.

Concern: runtime artifacts still fail closed because false-negative review/preflight remains `defer` / `OPERATOR_REVIEW_REQUIRED`. Next blocker is `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING`.
