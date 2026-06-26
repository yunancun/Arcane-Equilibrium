# Authorization Gate Status Clarity Runtime Sync

Date: 2026-06-26 08:53 CEST

本輪只把 v556 source fix 同步到 Linux runtime。

已完成：

- Linux runtime source: `785a4346 -> 99d3b8f7`
- Crontab expected-head literals: old `11 -> 0`, new `0 -> 11`
- Crontab line count: `70 -> 70`
- API service stayed active; MainPID remained `2218842`
- Runtime focused tests passed:
  - auth `19 passed`
  - scorecard `18 passed`
  - alpha discovery focused `6 passed`

沒有做：

- 沒有 restart / rebuild
- 沒有 manual cron
- 沒有寫 PG
- 沒有 Bybit/API/order/cancel/modify
- 沒有改 Cost Gate / cap / risk
- 沒有 grant probe/order/live authority
- 沒有宣稱 proof / promotion / PnL

注意：

- 這只是讓未來 scheduled cron 使用新的 false-negative status wording。
- 現有 `_latest` artifact 未被手動刷新，可能仍顯示舊 wording。
- 下一個 blocker 仍是 `P0-BOUNDED-PROBE-AUTHORIZATION`，但沒有新的 candidate-scoped auth delta 前不得重跑 read-only audit。
