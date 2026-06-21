# Runtime Demo Accumulation Read-Only Audit

日期：2026-06-21
狀態：只讀 runtime 取證

## 核心結論

demo 仍在累積 Cost Gate reject 數據，但沒有恢復真正下單/成交驗證，也沒有啟動 cost-gate learning lane。

近 1h demo/live_demo：

- decision features：2496
- cost-gate features：2496
- risk cost-gate rejects：2496
- intents/orders/fills：0 / 0 / 0

近 4h：

- decision features / cost-gate features / risk rejects：24536 / 24536 / 24536
- intents/orders/fills：0 / 0 / 0

這說明新信號不是 silent 丟失；它們有進 PG。但被 Cost Gate 擋掉後，目前 runtime 沒有把它們轉成 ledger/outcome learning evidence。

## Runtime 阻塞

- runtime source 還在 `917be4cc`
- runtime local `origin/main` 仍是 `1401848b`
- Mac 最新已推到 `42f77f36`
- runtime checkout dirty/untracked 很多
- learning lane 只有舊 plan artifact
- 沒有 heartbeat/status log/ledger/materializer/outcome review
- running engine 沒有 `OPENCLAW_DEMO_LEARNING_LANE_*` writer env
- alpha latest 還是舊 schema v1，仍錯誤顯示 actionable flags

## 下一步

不是再寫 source wrapper，而是需要 operator 授權 runtime source reconcile/sync + preflight + cron/writer activation。否則 demo 會繼續記錄 reject，但不會形成自主學習閉環。

本次沒有做任何 runtime 寫入、PG 寫入、crontab 修改、env 修改、重啟、Bybit private/signed/trading call、下單授權或 Cost Gate lowering。
