# 2026-06-22 — Sealed Horizon Bounded Demo-Probe Preflight

## 結論

新增 `sealed_horizon_bounded_demo_probe_preflight_v1`。它把 `ma_crossover|BTCUSDT|Sell@240m` 這類 sealed candidate 的 probe 前檢查變成機器可讀 gate。

目前這不是 probe approval，也不會下單。它只會指出還缺什麼：operator review、production learning lane 積累、或 authority boundary 是否被破壞。

## 本次改動

- 新增 `sealed_horizon_probe_preflight.py`。
- alpha discovery / learning worklist 會讀取 preflight latest artifact。
- 如果 preflight 存在，worklist 會顯示更精確的 blocker，例如 operator review + production lane accumulation 都還缺。

## 邊界

- 沒有 PG write/schema migration
- 沒有 Bybit private/signed/trading call
- 沒有 deploy/restart
- 沒有 env/auth/risk/order/strategy mutation
- 沒有 lowering Cost Gate
- 沒有 probe/order authority
- 沒有 promotion proof

## 下一個合理決策

先用 preflight artifact 審 `ma_crossover|BTCUSDT|Sell@240m`。只有當 operator review 記錄存在，且 production learning lane 在真 demo runtime 持續積累 ledger/outcome rows 後，才值得另開 Rust-authority bounded demo probe authorization。
