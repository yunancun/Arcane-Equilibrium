# Standing Demo Authorization Plumbing Source Fix

Status: `DONE_WITH_CONCERNS`

本輪完成 source/test/docs plumbing：valid `standing_demo_operator_authorization_v1` 現在能自動派生 candidate-scoped bounded Demo authorization id/budget/expiry，兩條 cron refresh chain 也能透過顯式 standing JSON path 消費該 envelope。缺省仍是 `defer`，且 cron 不注入 raw operator-id/auth-id/typed-confirm。

驗證：auth focused `21 passed`、cron static `24 passed`、adjacent alpha/profitability `140 passed`、bash syntax、py_compile、`git diff --check` 均通過。本輪沒有 runtime sync、Bybit/API/order/cancel/modify、PG query/write、Cost Gate lowering、writer/adapter enablement、active probe/order/live authority 或 profit proof。

下一步：`P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-AUTH-PLUMBING-SYNC-REVIEW`，先做 E3-reviewed runtime source/expected-head sync，再允許 runtime artifacts consume standing envelope。
