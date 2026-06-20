# Polymarket Jitter-Tolerant Sample Floor

已完成：Polymarket lead-lag IC v0.5 現在對 15m cron timestamp jitter 使用 5s tolerance 來計算 non-overlap sample floor 與 HAC lag，避免 intended 15m samples 因幾百毫秒到數秒的啟動差異被誤判為 overlapping。

這不是放寬 alpha gate：min_points、HAC t-stat、BH q-value gate 全部維持。Runtime v0.5 smoke `2026-06-20T14:39:41Z` latest sha256 `8756b1c5758634f283de79fc83014cd12b290c3fd0c79669c6bbef8f2b7d2136`，adjusted sample_count=9，仍 `INSUFFICIENT_SAMPLE` below gate 30。Alpha discovery `14:39:57Z` reports `polymarket_leadlag_ic.sample_count=9`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0。

邊界：read-only artifact/status only；無 engine restart、無下單、無 auth/risk/order/strategy 變更，非 promotion proof。
