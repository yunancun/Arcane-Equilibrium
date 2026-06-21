# Cost Gate Source Reconcile Manifest

日期：2026-06-22
狀態：source/test/docs checkpoint 完成

## 核心結論

我補了一個 operator activation 前需要的可見性：Cost Gate learning activation preflight 現在不只會說 runtime source 是 dirty/behind，還會輸出可機讀的 source reconcile manifest。

它會告訴我們：

- 是否需要 source reconcile
- 原因是 dirty path、behind upstream、expected head mismatch 等哪一類
- 下一步 action
- dirty/tracked/untracked path manifest
- manifest 是否被截斷

這不是 runtime sync，也不是授權；只是讓下一步授權前不需要人工從一長串 `git status` 裡猜該處理什麼。

## Runtime 事實仍未變

今天只讀核實後，阻塞仍然存在：

- `trade-core` source 仍在 `917be4cc`
- local `origin/main` 仍是 `1401848b`
- checkout 仍 behind 5 且 dirty/untracked
- learning lane 仍只有舊 plan，沒有 heartbeat/status/ledger/outcome artifacts
- engine 仍沒有 `OPENCLAW_DEMO_LEARNING_LANE_*` writer env
- demo/live_demo rejects 仍在 PG 累積，但 orders/fills 沒恢復
- alpha latest 仍是舊 schema v1，仍不能作為 actionable 判斷依據

## 邊界

沒有 runtime source sync、沒有 artifact refresh、沒有 crontab/env 修改、沒有 deploy/rebuild/restart、沒有 PG 寫入、沒有 Bybit private/signed/trading call、沒有 order authority、沒有 lower Cost Gate。

下一步仍需要你明確授權 runtime source reconcile/sync；授權後才進 preflight、preinstall refresh、cron/writer activation。
