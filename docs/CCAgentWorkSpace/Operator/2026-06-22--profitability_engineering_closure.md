# 2026-06-22 — Profitability Engineering Closure

## 結論

我把盈利路徑做成了更明確的工程閉環：profitability scorecard 現在會讀 sealed-horizon probe preflight，並輸出 `profitability_engineering_closure_v1`。

現在的主路不是降低全局 Cost Gate，而是用 `ma_crossover|BTCUSDT|Sell@240m` 這條 sealed horizon path 翻越 cost gate。它目前還缺兩件事：

- operator review 記錄
- production learning lane 真實累積 ledger/outcome rows

## 本次改動

- `profitability_path_scorecard.py` 新增 `--sealed-horizon-probe-preflight-json`。
- top path 會被 preflight 狀態精確分類，而不是只停在「需要 operator review」。
- 新增 closure 欄位，直接列出剩餘 proof gates、edge amplification levers、autonomous learning requirements。

## Linux smoke

- artifact：`/tmp/openclaw/profitability_refresh/20260622T031320Z/profitability_closure_v392/profitability_path_scorecard_latest.json`
- sha256：`9afb127096f78d20f31bdf2a39fdc5bec4a89784fb4842026150a354ed3534aa`
- closure：`COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_AND_PRODUCTION_LEARNING_LANE`
- remaining proof gates：2
- Cost Gate lowering：`false`
- probe authority：`false`
- order authority：`false`

## 邊界

- 沒有 PG write/schema migration
- 沒有 Bybit private/signed/trading call
- 沒有 deploy/restart
- 沒有 env/auth/risk/order/strategy mutation
- 沒有 lowering Cost Gate
- 沒有 probe/order authority
- 沒有 promotion proof

## 下一個合理決策

先不要降低全局 Cost Gate。下一步應該讓 production learning lane 真正在 demo runtime 積累數據，並把 operator review 記錄成 artifact。這兩件事完成後，才值得另開 Rust-authority bounded demo probe authorization。
