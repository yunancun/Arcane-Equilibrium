# Polymarket Pre-Gate HAC Watchlist

已完成：Polymarket lead-lag IC v0.6 現在會顯示 diagnostic-only `pre_gate_hac_watchlist`。這些是 HAC/BH 顯著但仍被 sample floor 擋住的 cells，用於追蹤，不是 signal、probe、promotion proof。

Runtime v0.6 smoke：`2026-06-20T14:50:18Z`，latest sha256 `864151680dc2787a79a387d7316faedb81568dc569ca2561ef1b38c723621213`，adjusted sample_count=9，watchlist_count=5，best watch `other|BTCUSDT|15m`，sample_gap=21，candidate_count=0，仍 `INSUFFICIENT_SAMPLE`。Alpha discovery `14:50:33Z` 也已 passthrough best watch，但 action 仍是 `RUN_READ_ONLY_CAPTURE`，ready/probe=0。

邊界：read-only artifact/status only；無 engine restart、無下單、無 auth/risk/order/strategy 變更，非 promotion proof。
