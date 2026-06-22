# 2026-06-22 — Sealed Horizon Alpha Worklist Bridge

## 結論

v390 已把 `OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE` 接入 alpha discovery 和 learning worklist。也就是說，`ma_crossover|BTCUSDT|Sell@240m` 這類 sealed horizon evidence 不會只停在 packet 報告裡，而會進入自主學習隊列，等待 operator review。

這是合理翻越 Cost Gate 的路徑：不全局 lower gate，而是針對被擋掉但事後有正期望的 side-cell/horizon 做 sealed evidence -> operator review -> bounded demo probe preflight。

## 本次改動

- runtime summary 會攜帶 sealed horizon evidence fields。
- alpha discovery 將該狀態分類為 `READY_FOR_PROBE` review blocker。
- learning worklist 產生 `operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe` 目標。

## 邊界

- 沒有 PG write/schema migration
- 沒有 Bybit private/signed/trading call
- 沒有 deploy/restart
- 沒有 env/auth/risk/order/strategy mutation
- 沒有 lowering Cost Gate
- 沒有 probe/order authority
- 沒有 promotion proof

## 下一個合理決策

先審 sealed evidence，並確認 production learning lane 能在 demo runtime 持續積累 ledger/outcome rows；在這之前，不應把全局 Cost Gate 降低當成盈利修復。
