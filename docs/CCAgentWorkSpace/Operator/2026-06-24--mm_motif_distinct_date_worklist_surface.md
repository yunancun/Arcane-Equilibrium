# Operator Note — MM Motif Distinct-Date Worklist Surface

日期：2026-06-24
狀態：`DONE_WITH_CONCERNS`

## 你需要知道的事

本輪把 MM 的兩條盈利研究路徑在 worklist 裡拆開了：

- `mm_current_fee_confirmation`：確認同一個 SOXLUSDT current-fee positive exact cell 是否能在第二個獨立 window 重複。
- `mm_motif_distinct_date_accumulation`：確認 low-friction MM motif 是否能跨 distinct dates 重複，而不是只停留在單次窗口或 artifact 設計。

Runtime 已同步到 source commit `52b572eda6c5652c97d2e822de9a9670250629a6`，crontab expected-head pins 也同步。Alpha refresh at `2026-06-24T15:12:51Z` 已看到兩個 MM tasks，且兩者都明確是：

- `requires_operator_authorization=false`
- `runtime_mutation_required=false`
- no order/probe authority
- no Cost Gate mutation
- no promotion proof

## 你的全權 Demo API 授權如何處理

我會把你的最新授權記為 standing Demo-only operational permission：Demo API / Demo runtime 方向如果有安全、候選已界定、可重建的動作，後續不會反覆問你同一類「是否可操作 Demo」。

但這不等於 live/mainnet 權限，也不等於放寬證據規則。為了讓 Demo 經驗後續能 apply live，任何有交易含義的 Demo probe 仍要保留：

- exact candidate / symbol / side / horizon
- max order / expiry / risk boundary
- fees/slippage/net PnL after costs
- candidate-matched order/fill lineage
- matched controls
- Guardian / Decision Lease / Rust authority / reconstructability

這樣 Demo 不是一次性人工操作，而是能被 live 路徑重放、審計、比較和拒絕的經驗。

## 下一個安全方向

不要把本輪當成盈利 proof。下一步安全工作是讓 alpha loop 累積或 replay：

- MM motif 的 distinct-date repeat evidence
- SOXLUSDT current-fee exact-cell 的第二個 independent window
- false-negative AVAX path 的 candidate-matched bounded Demo packet / outcome chain

禁止仍然不變：

- 不降低 global Cost Gate
- 不宣稱 artifact 數量、單窗口 MM positive、replay-only result 是盈利 proof
- 不 count unattributed fills
- 不 live promotion
- 不把 Demo 經驗當作 live 可用，除非通過完整可重建鏈
