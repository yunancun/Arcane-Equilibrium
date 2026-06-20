# Operator Note — Polymarket Pre-Gate Watchlist Persistence

日期：2026-06-20

這批新增的是診斷，不是交易變更。

`polymarket_leadlag` v0.13 現在會看最近多份 Polymarket lead-lag report，判斷 pre-gate HAC watchlist cell 是否跨報告持續出現。最新 runtime 結果：

- Polymarket latest sha256 `c64314139cac2349fdb1983de593a20c58fcac5813b0511d56c4ad4ae3ea65f5`
- `INSUFFICIENT_SAMPLE`, sample `19/30`
- `pre_gate_watchlist_persistence_status=LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST`
- recurring=5, persistent=5
- floor-qualified recurring=0, persistent=0
- top recurring cells 都是 240m，current sample floor=1；目前 stronger-watch floor threshold=8

解讀：Polymarket 確實有反覆出現的 pre-gate 線索，但樣本太薄，不能當候選、不能 probe、不能 promotion。Alpha discovery latest sha256 `76d8778a1964faaa93dcd81060ecc7afcbb3dcf08e52fbfeb269b9d166f319b8` 仍是 `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`。

驗證：Mac/Linux focused suite `78 passed`，py_compile、shell syntax、diff-check passed。邊界：source/test/docs + `/tmp/openclaw` artifact/status writes only；沒有 PG write、Bybit private/signed/trading call、engine/API restart、strategy/risk/order/auth mutation。
