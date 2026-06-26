# Operator Note - Standing Demo False-Negative Preflight Runtime Sync

Status: `DONE_WITH_CONCERNS`

Runtime `trade-core` is now fast-forwarded to `e29c96cc...`, and all 11 crontab expected-head pins point to that commit. Line count stayed 70; mainnet, adapter enablement, probe-record enablement, standing-envelope env, and explicit bounded-auth `authorize` env counts are all 0. API/watchdog stayed active with unchanged PIDs `2218842`/`1538268`.

Natural artifacts still fail closed: bounded auth is `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` with `decision=defer`, no auth object, and active probe/order authority false/false; profitability still lacks execution evidence.

No service restart, manual cron run, env mutation, standing-envelope materialization, PG/Bybit/order action, Cost Gate lowering, active authority, or profit proof occurred.

Full report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-27--standing_demo_false_negative_preflight_runtime_sync_apply.md`
