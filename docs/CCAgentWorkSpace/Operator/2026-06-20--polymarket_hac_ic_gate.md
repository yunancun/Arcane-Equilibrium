# Polymarket HAC IC Gate

已完成：Polymarket lead-lag IC 現在用 Newey-West/HAC t-stat + BH q-value 控制候選，naive t-stat 只保留作診斷，避免 15m cadence 下序列相關造成假陽性。

Runtime v0.4 smoke：`2026-06-20T13:03:57Z`，latest sha256 `9e4941dc399f5f6c2c08076814d06f3ed78b6084d383689f66800083c80a5601`，adjusted sample_count=2，仍 `INSUFFICIENT_SAMPLE`。Alpha discovery `13:04:14Z` 仍是 `RUN_READ_ONLY_CAPTURE`，ready/probe=0。

邊界：read-only artifact/status only；無 engine restart、無下單、無 auth/risk/order/strategy 變更，非 promotion proof。
