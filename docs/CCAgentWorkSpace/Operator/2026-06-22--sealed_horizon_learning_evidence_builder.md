# 2026-06-22 — Sealed Horizon Learning Evidence Builder

## 結論

我們已把 `ma_crossover|BTCUSDT|Sell` 240m sealed candidate 轉成可重跑的 blocked-signal learning evidence。Linux smoke 顯示 16,515 條成熟 reject 在 240m 下平均 net `+3.0511bp`、net-positive `68.56%`，達到 `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`。

這支持 operator review 一個 bounded demo probe，不支持全局降低 Cost Gate。

## 本次改動

- 新增 `sealed_horizon_learning_evidence.py`
- 它串起：mature reject extraction -> scratch ledger -> 240m blocked outcome -> review packet
- 只接受 sealed horizon candidate
- 所有輸出仍是 artifact-only

## 邊界

- 沒有 PG write/schema migration
- 沒有 Bybit private/signed/trading call
- 沒有 deploy/restart
- 沒有 env/auth/risk/order/strategy mutation
- 沒有 lowering Cost Gate
- 沒有 probe/order authority
- 沒有 promotion proof

## 下一個合理決策

不要全局 lower Cost Gate。應先把 production learning lane writer/cron/prod ledger 啟用到能持續產生這類 evidence，然後只對 `ma_crossover|BTCUSDT|Sell@240m` 這類已通過 review 的 side-cell 設計極小、operator-gated、Rust-authority demo probe。
