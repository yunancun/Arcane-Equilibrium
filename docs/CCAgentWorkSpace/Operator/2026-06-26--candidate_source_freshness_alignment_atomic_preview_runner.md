# Operator Note: Candidate Source Freshness Alignment + Atomic Preview Runner

Status: `DONE_WITH_CONCERNS`

本輪完成了兩件事：

1. 修正 AVAX Sell candidate source handoff：fresh reroute packet 現在帶上 `current_cap_usdt=10.0`，不再因只看到 `cap_usdt` 而讓 adapter/preview 失去 cap 資訊。
2. 新增並執行一次 E3/BB-reviewed atomic runner，把 public quote capture -> adapter -> no-order construction preview 放在同一進程內，避免手工分步時 quote 超過 `1000ms` freshness window。

結果：AVAX Sell no-order construction preview ready。它只證明「在當時 public BBO 下可構造一個符合 cap/filter 的 no-order preview」，不是下單授權、不是 bounded-probe proof，也不是盈利證明。

重要邊界：

- 沒有下單、撤單、改單。
- 沒有 private Bybit call。
- 沒有 PG query/write。
- 沒有 runtime/service/env/crontab mutation。
- 沒有降低 Cost Gate 或 freshness gate。
- 沒有授予 probe/order/live authority。

下一步先暫停。若要進 P0 bounded Demo probe，仍需要 candidate-scoped 授權物件或精確 typed confirm，再走 PM -> E3 -> BB；廣義「demo API 可以操作」不能直接繞過 repo authorization gates。
