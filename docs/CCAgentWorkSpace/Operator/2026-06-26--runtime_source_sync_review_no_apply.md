# Operator Note: Runtime Source Sync Review No-Apply

Status: `DONE_WITH_CONCERNS`

本輪只做 review，沒有做 runtime apply。

結論：

- Mac/source 和 GitHub `origin/main` 現在是 `beeef498...`。
- Linux runtime 還在 `dd22810e...`，且 11 條 cron expected-head pin 也都指向 `dd22810e...`。
- 這是 drift，但 runtime 內部一致，所以現在不需要立刻 apply。
- E3 沒找到未來 source-sync 的安全 blocker。

如果未來要 apply，必須另開一輪，且 apply envelope 只能是：

1. runtime repo fast-forward `dd22810e... -> beeef498...`
2. 同一 checkpoint 內把 11 條 expected-head pin 全部改到 `beeef498...`
3. 保持 crontab 行數不變
4. post-check runtime clean、old pin count `0`、new pin count `11`、API MainPID 不變、auth artifact 不變

本輪沒有：

- git pull runtime
- crontab edit
- service restart
- cron run
- PG query/write
- Bybit private/public call
- order/cancel/modify
- Cost Gate/freshness gate 變更
- probe/order/live authority grant

P0 真 blocker 還是 candidate-scoped authorization 缺失：最新 runtime auth 是 AVAX Sell `decision=defer`，沒有 authorization object，也沒有 active authority。
